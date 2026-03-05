"""ParentAgent — ZMQ ROUTER Host + Agent Registry + Message Router

AgentServer相当の役割。ZMQ ROUTERをbindし、子Agent(AgentShell)からの
DEALER接続を受け付ける。メッセージルーティング、ライフサイクル管理を担う。

Usage:
    parent = ParentAgent(router_port=5570)
    await parent.start()
    await parent.spawn_child("coder", "coder")
    await parent.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional

import zmq
import zmq.asyncio

from aetherterm.common.agent_protocol import (
    AgentMessage,
    MessageBuilder,
    MessageType,
)
from aetherterm.common.zmq_utils import pack_message, safe_create_task, unpack_message

from .child_launcher import ChildLauncher, SubprocessLauncher, TmuxPaneLauncher

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """登録済みAgentの情報"""

    agent_id: str
    role: str
    identity: bytes = b""  # ZMQ ROUTER identity
    status: str = "registered"
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class ParentAgent:
    """親Agent: ZMQ ROUTER + Agent Registry + Message Router

    AgentServerのZMQメッセージングハブとして機能。
    子Agent(AgentShell)をpaneで起動し、DEALER接続を受け付ける。
    """

    def __init__(
        self,
        agent_id: str = "parent",
        router_port: int = 5570,
        launcher: Optional[ChildLauncher] = None,
    ):
        self._agent_id = agent_id
        self._router_port = router_port
        self._router_addr = f"tcp://*:{router_port}"
        self._connect_addr = f"tcp://localhost:{router_port}"

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._router: Optional[zmq.asyncio.Socket] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._running = False

        # Agent Registry: agent_id → AgentInfo
        self._agents: Dict[str, AgentInfo] = {}
        # ZMQ identity → agent_id mapping
        self._identity_map: Dict[bytes, str] = {}

        # Child launcher (abstraction layer)
        self._launcher: ChildLauncher = launcher or SubprocessLauncher()

        # Task completion callbacks: task_id → Future
        self._task_futures: Dict[str, asyncio.Future] = {}

        # Event callbacks
        self._on_agent_registered: Optional[Callable] = None
        self._on_task_complete: Optional[Callable] = None
        self._on_message: Optional[Callable] = None

    @property
    def agents(self) -> Dict[str, AgentInfo]:
        return dict(self._agents)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def set_on_agent_registered(self, cb: Callable) -> None:
        self._on_agent_registered = cb

    def set_on_task_complete(self, cb: Callable) -> None:
        self._on_task_complete = cb

    def set_on_message(self, cb: Callable) -> None:
        """All received messages callback (for logging/debugging)"""
        self._on_message = cb

    async def start(self) -> None:
        """ROUTER bind + recv loop start"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.setsockopt(zmq.LINGER, 500)
        self._router.bind(self._router_addr)

        self._running = True
        self._recv_task = safe_create_task(
            self._recv_loop(), name="parent-recv-loop", logger=logger
        )

        logger.info(f"ParentAgent started: ROUTER bind {self._router_addr}")

    async def stop(self) -> None:
        """全子Agent shutdown + cleanup"""
        if not self._running:
            return

        logger.info("ParentAgent stopping...")

        # Send shutdown to all agents
        for agent_id in list(self._agents.keys()):
            try:
                await self._send_to_agent(
                    agent_id,
                    MessageBuilder.request_shutdown(
                        self._agent_id, agent_id, "Parent shutting down"
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to send shutdown to {agent_id}: {e}")

        # Wait briefly for graceful shutdown
        await asyncio.sleep(0.5)

        # Terminate all child processes
        for agent_id in list(self._agents.keys()):
            try:
                await self._launcher.terminate(agent_id)
            except Exception as e:
                logger.warning(f"Failed to terminate {agent_id}: {e}")

        self._running = False

        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        # Cancel pending task futures
        for fut in self._task_futures.values():
            if not fut.done():
                fut.cancel()
        self._task_futures.clear()

        if self._router:
            self._router.close()
        if self._ctx:
            self._ctx.term()

        self._agents.clear()
        self._identity_map.clear()

        logger.info("ParentAgent stopped")

    async def spawn_child(
        self,
        agent_id: str,
        role: str,
        command: Optional[str] = None,
    ) -> str:
        """子Agentをpaneで起動（launcher経由）

        Returns:
            agent_id (or pane_id from launcher)
        """
        child_id = await self._launcher.launch(
            agent_id=agent_id,
            role=role,
            router_addr=self._connect_addr,
            command=command,
        )
        logger.info(f"Spawned child: {agent_id} (role={role})")
        return child_id

    async def wait_for_agent(self, agent_id: str, timeout: float = 10.0) -> bool:
        """Agentの登録完了を待つ"""
        start = time.time()
        while time.time() - start < timeout:
            if agent_id in self._agents:
                return True
            await asyncio.sleep(0.1)
        logger.warning(f"Timeout waiting for agent {agent_id}")
        return False

    # --- Message Sending ---

    async def send_task(
        self,
        to_agent: str,
        task_type: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[asyncio.Future]:
        """子Agentにタスクを送信し、完了Futureを返す"""
        from uuid import uuid4

        task_id = str(uuid4())
        msg = AgentMessage(
            from_agent=self._agent_id,
            to_agent=to_agent,
            message_type=MessageType.TASK_CREATE,
            payload={
                "task_id": task_id,
                "task_type": task_type,
                "description": description,
                "context": context or {},
            },
        )
        await self._send_to_agent(to_agent, msg)

        # Create a future for task completion
        fut = asyncio.get_event_loop().create_future()
        self._task_futures[task_id] = fut
        return fut

    async def send_dm(self, to_agent: str, content: str) -> None:
        """特定のAgentにDMを送信"""
        msg = MessageBuilder.send_dm(self._agent_id, to_agent, content)
        await self._send_to_agent(to_agent, msg)

    async def broadcast(self, content: str) -> None:
        """全Agentにブロードキャスト"""
        msg = MessageBuilder.send_broadcast(self._agent_id, content)
        for agent_id in list(self._agents.keys()):
            try:
                await self._send_to_agent(agent_id, msg)
            except Exception as e:
                logger.warning(f"Broadcast to {agent_id} failed: {e}")

    # --- Internal ---

    async def _send_to_agent(self, agent_id: str, msg: AgentMessage) -> None:
        """指定AgentにZMQ ROUTERメッセージを送信"""
        info = self._agents.get(agent_id)
        if not info:
            logger.warning(f"Agent {agent_id} not registered, cannot send")
            return
        if not info.identity:
            logger.warning(f"Agent {agent_id} has no identity, cannot send")
            return

        packed = pack_message(msg.to_dict())
        await self._router.send_multipart([info.identity, packed])
        logger.debug(f"Sent {msg.message_type.value} to {agent_id}")

    async def _recv_loop(self) -> None:
        """ROUTER recv loop: [identity, msgpack(AgentMessage)]"""
        poller = zmq.asyncio.Poller()
        poller.register(self._router, zmq.POLLIN)

        try:
            while self._running:
                events = dict(await poller.poll(timeout=500))
                if self._router not in events:
                    continue

                frames = await self._router.recv_multipart()
                if len(frames) < 2:
                    continue

                identity = frames[0]
                try:
                    data = unpack_message(frames[1])
                    msg = AgentMessage.from_dict(data)
                except Exception as e:
                    logger.error(f"Failed to parse message: {e}")
                    continue

                # Notify callback
                if self._on_message:
                    try:
                        result = self._on_message(msg)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass

                await self._handle_message(identity, msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"recv_loop error: {e}", exc_info=True)

    async def _handle_message(self, identity: bytes, msg: AgentMessage) -> None:
        """受信メッセージのディスパッチ"""
        mt = msg.message_type

        if mt == MessageType.AGENT_REGISTER:
            await self._handle_register(identity, msg)

        elif mt == MessageType.AGENT_UNREGISTER:
            self._handle_unregister(msg)

        elif mt == MessageType.AGENT_HEARTBEAT:
            self._handle_heartbeat(msg)

        elif mt == MessageType.AGENT_DM:
            # DM: to_agentにルーティング
            await self._route_dm(msg)

        elif mt == MessageType.AGENT_BROADCAST:
            # Broadcast: 全agentに配信（送信元除く）
            await self._handle_broadcast(msg)

        elif mt == MessageType.TASK_COMPLETE:
            self._handle_task_complete(msg)

        elif mt == MessageType.TASK_FAILED:
            self._handle_task_failed(msg)

        elif mt == MessageType.AGENT_IDLE:
            info = self._agents.get(msg.from_agent)
            if info:
                info.status = "idle"
                logger.debug(f"Agent {msg.from_agent} → idle")

        elif mt == MessageType.AGENT_BUSY:
            info = self._agents.get(msg.from_agent)
            if info:
                info.status = "busy"
                logger.debug(f"Agent {msg.from_agent} → busy")

        elif mt == MessageType.SHUTDOWN_RESPONSE:
            logger.info(
                f"Agent {msg.from_agent} shutdown response: "
                f"approve={msg.payload.get('approve')}"
            )

        else:
            logger.warning(f"Unhandled message type: {mt.value} from {msg.from_agent}")

    async def _handle_register(self, identity: bytes, msg: AgentMessage) -> None:
        """AGENT_REGISTER処理: registryに登録してACK返信"""
        agent_id = msg.from_agent
        role = msg.payload.get("role", "unknown")

        info = AgentInfo(
            agent_id=agent_id,
            role=role,
            identity=identity,
        )
        self._agents[agent_id] = info
        self._identity_map[identity] = agent_id

        logger.info(f"Agent registered: {agent_id} (role={role})")

        # ACK返信
        ack = AgentMessage(
            from_agent=self._agent_id,
            to_agent=agent_id,
            message_type=MessageType.REGISTRATION_CONFIRMED,
            payload={"agent_id": agent_id, "status": "registered"},
        )
        packed = pack_message(ack.to_dict())
        await self._router.send_multipart([identity, packed])

        if self._on_agent_registered:
            try:
                result = self._on_agent_registered(agent_id, role)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def _handle_unregister(self, msg: AgentMessage) -> None:
        agent_id = msg.from_agent
        info = self._agents.pop(agent_id, None)
        if info and info.identity:
            self._identity_map.pop(info.identity, None)
        logger.info(f"Agent unregistered: {agent_id}")

    def _handle_heartbeat(self, msg: AgentMessage) -> None:
        agent_id = msg.from_agent
        info = self._agents.get(agent_id)
        if info:
            info.last_seen = time.time()

    async def _route_dm(self, msg: AgentMessage) -> None:
        """DMを宛先Agentにルーティング"""
        to = msg.to_agent
        if to == self._agent_id:
            # 親宛のDM
            logger.info(
                f"DM from {msg.from_agent} → parent: "
                f"{msg.payload.get('content', '')[:80]}"
            )
            return

        if to not in self._agents:
            logger.warning(f"DM target {to} not found, dropping message")
            return

        await self._send_to_agent(to, msg)
        logger.debug(f"Routed DM: {msg.from_agent} → {to}")

    async def _handle_broadcast(self, msg: AgentMessage) -> None:
        """Broadcastを全Agent(送信元除く)に配信"""
        sender = msg.from_agent
        for agent_id in list(self._agents.keys()):
            if agent_id != sender:
                try:
                    await self._send_to_agent(agent_id, msg)
                except Exception as e:
                    logger.warning(f"Broadcast to {agent_id} failed: {e}")
        logger.debug(f"Broadcast from {sender} delivered to {len(self._agents) - 1} agents")

    def _handle_task_complete(self, msg: AgentMessage) -> None:
        """TASK_COMPLETE処理"""
        task_id = msg.payload.get("task_id")
        result = msg.payload.get("result", {})
        logger.info(f"Task {task_id} completed by {msg.from_agent}")

        fut = self._task_futures.pop(task_id, None)
        if fut and not fut.done():
            fut.set_result({"agent": msg.from_agent, "result": result})

        if self._on_task_complete:
            try:
                r = self._on_task_complete(msg.from_agent, task_id, result)
                if asyncio.iscoroutine(r):
                    asyncio.ensure_future(r)
            except Exception:
                pass

    def _handle_task_failed(self, msg: AgentMessage) -> None:
        """TASK_FAILED処理"""
        task_id = msg.payload.get("task_id")
        error = msg.payload.get("error", "unknown error")
        logger.warning(f"Task {task_id} failed by {msg.from_agent}: {error}")

        fut = self._task_futures.pop(task_id, None)
        if fut and not fut.done():
            fut.set_exception(RuntimeError(f"Task failed: {error}"))


# --- CLI Entry Point ---

async def main():
    """Standalone ROUTER host for testing"""
    import argparse

    parser = argparse.ArgumentParser(description="ParentAgent ROUTER host")
    parser.add_argument("--port", type=int, default=5570)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parent = ParentAgent(router_port=args.port)

    def on_registered(agent_id, role):
        print(f"  ✓ Agent registered: {agent_id} (role={role})")

    def on_msg(msg):
        print(f"  ← [{msg.from_agent}] {msg.message_type.value}: {msg.payload}")

    parent.set_on_agent_registered(on_registered)
    parent.set_on_message(on_msg)

    await parent.start()
    print(f"ParentAgent ROUTER listening on :{args.port}")
    print("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await parent.stop()


if __name__ == "__main__":
    asyncio.run(main())
