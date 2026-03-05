"""ChildAgent — ZMQ DEALER Client + Message Handler

AgentShell相当の役割。DEALERで親(AgentServer)のROUTERに接続し、
タスク実行、DM送受信、ブロードキャスト受信を行う。

Usage (standalone):
    python -m experimental.zmq_agent_poc.child_agent \
        --agent-id coder --role coder --router tcp://localhost:5570

Usage (in code):
    child = ChildAgent("coder", "coder")
    child.on_task(handle_task)
    await child.start()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

import zmq
import zmq.asyncio

from aetherterm.common.agent_protocol import (
    AgentMessage,
    MessageBuilder,
    MessageType,
)
from aetherterm.common.zmq_utils import pack_message, safe_create_task, unpack_message

logger = logging.getLogger(__name__)


class ChildAgent:
    """子Agent: ZMQ DEALER + message handler

    AgentShellとして、親のROUTERにDEALER接続し、
    メッセージベースでタスク実行やAgent間通信を行う。
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        router_addr: str = "tcp://localhost:5570",
    ):
        self._agent_id = agent_id
        self._role = role
        self._router_addr = router_addr

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._dealer: Optional[zmq.asyncio.Socket] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._registered = False

        # Message handlers: MessageType → async callback
        self._handlers: Dict[MessageType, Callable] = {}

        # Pending tasks tracking
        self._current_task: Optional[Dict[str, Any]] = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_running(self) -> bool:
        return self._running

    # --- Handler Registration ---

    def on_message(self, msg_type: MessageType):
        """デコレータでメッセージハンドラを登録

        @child.on_message(MessageType.TASK_CREATE)
        async def handle_task(msg: AgentMessage):
            ...
        """

        def decorator(func: Callable):
            self._handlers[msg_type] = func
            return func

        return decorator

    def on_task(self, handler: Callable) -> None:
        """TASK_CREATEハンドラを直接登録"""
        self._handlers[MessageType.TASK_CREATE] = handler

    def on_dm(self, handler: Callable) -> None:
        """AGENT_DMハンドラを直接登録"""
        self._handlers[MessageType.AGENT_DM] = handler

    # --- Lifecycle ---

    async def start(self) -> None:
        """DEALER connect + register + recv loop"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()
        self._dealer = self._ctx.socket(zmq.DEALER)
        # Set identity to agent_id for ROUTER routing
        self._dealer.setsockopt(zmq.IDENTITY, self._agent_id.encode())
        self._dealer.setsockopt(zmq.LINGER, 500)
        self._dealer.connect(self._router_addr)

        self._running = True

        # Send AGENT_REGISTER
        register_msg = AgentMessage(
            from_agent=self._agent_id,
            to_agent="parent",
            message_type=MessageType.AGENT_REGISTER,
            payload={"role": self._role, "agent_id": self._agent_id},
        )
        await self._send(register_msg)

        # Start recv loop
        self._recv_task = safe_create_task(
            self._recv_loop(), name=f"child-{self._agent_id}-recv", logger=logger
        )

        # Start heartbeat
        self._heartbeat_task = safe_create_task(
            self._heartbeat_loop(), name=f"child-{self._agent_id}-hb", logger=logger
        )

        logger.info(
            f"ChildAgent started: id={self._agent_id}, role={self._role}, "
            f"router={self._router_addr}"
        )

    async def stop(self) -> None:
        """AGENT_UNREGISTER + cleanup"""
        if not self._running:
            return

        logger.info(f"ChildAgent {self._agent_id} stopping...")

        # Send unregister
        try:
            unreg = AgentMessage(
                from_agent=self._agent_id,
                to_agent="parent",
                message_type=MessageType.AGENT_UNREGISTER,
                payload={"agent_id": self._agent_id},
            )
            await self._send(unreg)
        except Exception:
            pass

        self._running = False

        for task in [self._recv_task, self._heartbeat_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._dealer:
            self._dealer.close()
        if self._ctx:
            self._ctx.term()

        logger.info(f"ChildAgent {self._agent_id} stopped")

    # --- Message Sending ---

    async def send_dm(self, to_agent: str, content: str, summary: str = "") -> None:
        """DMを送信"""
        msg = MessageBuilder.send_dm(self._agent_id, to_agent, content, summary)
        await self._send(msg)
        logger.debug(f"Sent DM to {to_agent}")

    async def send_broadcast(self, content: str, summary: str = "") -> None:
        """ブロードキャスト送信（親経由で全Agentに配信）"""
        msg = MessageBuilder.send_broadcast(self._agent_id, content, summary)
        await self._send(msg)

    async def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """タスク完了を親に通知"""
        from uuid import UUID

        msg = MessageBuilder.complete_task(
            self._agent_id, "parent", UUID(task_id), result
        )
        await self._send(msg)
        self._current_task = None
        logger.info(f"Task {task_id} completed")

        # Signal idle
        idle_msg = MessageBuilder.signal_idle(self._agent_id)
        await self._send(idle_msg)

    async def fail_task(self, task_id: str, error: str) -> None:
        """タスク失敗を親に通知"""
        from uuid import UUID

        msg = MessageBuilder.fail_task(self._agent_id, "parent", UUID(task_id), error)
        await self._send(msg)
        self._current_task = None

    # --- AI Integration Stub ---

    async def think(self, prompt: str) -> str:
        """AI呼び出しスタブ

        将来: IndependentAIService / LangChain統合
        現在: 簡易的なrole-basedスタブ応答
        """
        await asyncio.sleep(0.3)  # Simulate AI latency

        role_responses = {
            "coder": self._stub_coder,
            "reviewer": self._stub_reviewer,
            "tester": self._stub_tester,
        }
        stub = role_responses.get(self._role, self._stub_default)
        return stub(prompt)

    def _stub_coder(self, prompt: str) -> str:
        if "fibonacci" in prompt.lower():
            return (
                "def fibonacci(n: int) -> int:\n"
                '    """Return the nth Fibonacci number."""\n'
                "    if n <= 1:\n"
                "        return n\n"
                "    a, b = 0, 1\n"
                "    for _ in range(2, n + 1):\n"
                "        a, b = b, a + b\n"
                "    return b\n"
            )
        return f"# Code implementation for: {prompt}\npass"

    def _stub_reviewer(self, prompt: str) -> str:
        return (
            "Code Review:\n"
            "- ✓ Function signature is clean\n"
            "- ✓ Edge cases handled (n <= 1)\n"
            "- ✓ Iterative approach (O(n) time, O(1) space)\n"
            "- ⚠ Consider adding input validation for negative n\n"
            "- Overall: APPROVED with minor suggestion"
        )

    def _stub_tester(self, prompt: str) -> str:
        return (
            "import pytest\n\n"
            "def test_fibonacci_base_cases():\n"
            "    assert fibonacci(0) == 0\n"
            "    assert fibonacci(1) == 1\n\n"
            "def test_fibonacci_sequence():\n"
            "    assert fibonacci(5) == 5\n"
            "    assert fibonacci(10) == 55\n\n"
            "def test_fibonacci_large():\n"
            "    assert fibonacci(20) == 6765\n"
        )

    def _stub_default(self, prompt: str) -> str:
        return f"Processed: {prompt}"

    # --- Internal ---

    async def _send(self, msg: AgentMessage) -> None:
        """DEALERでメッセージ送信"""
        if not self._dealer or not self._running:
            return
        packed = pack_message(msg.to_dict())
        await self._dealer.send(packed)

    async def _recv_loop(self) -> None:
        """DEALER recv loop: [msgpack(AgentMessage)]"""
        poller = zmq.asyncio.Poller()
        poller.register(self._dealer, zmq.POLLIN)

        try:
            while self._running:
                events = dict(await poller.poll(timeout=500))
                if self._dealer not in events:
                    continue

                raw = await self._dealer.recv()
                try:
                    data = unpack_message(raw)
                    msg = AgentMessage.from_dict(data)
                except Exception as e:
                    logger.error(f"Failed to parse message: {e}")
                    continue

                await self._dispatch(msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"recv_loop error: {e}", exc_info=True)

    async def _dispatch(self, msg: AgentMessage) -> None:
        """受信メッセージをハンドラにディスパッチ"""
        mt = msg.message_type

        if mt == MessageType.REGISTRATION_CONFIRMED:
            self._registered = True
            logger.info(f"Registration confirmed by parent")
            return

        if mt == MessageType.SHUTDOWN_REQUEST:
            logger.info(f"Shutdown requested by {msg.from_agent}")
            # Auto-approve shutdown
            resp = MessageBuilder.respond_shutdown(
                self._agent_id,
                msg.from_agent,
                str(msg.message_id),
                approve=True,
                content="Shutting down gracefully",
            )
            await self._send(resp)
            await self.stop()
            return

        # Custom handler
        handler = self._handlers.get(mt)
        if handler:
            try:
                # Signal busy
                busy_msg = MessageBuilder.signal_busy(self._agent_id)
                await self._send(busy_msg)

                result = handler(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Handler error for {mt.value}: {e}", exc_info=True)
        else:
            logger.debug(f"No handler for {mt.value}, ignored")

    async def _heartbeat_loop(self) -> None:
        """定期的にheartbeatを送信"""
        try:
            while self._running:
                await asyncio.sleep(10.0)
                hb = AgentMessage(
                    from_agent=self._agent_id,
                    to_agent="parent",
                    message_type=MessageType.AGENT_HEARTBEAT,
                    payload={"timestamp": time.time()},
                )
                await self._send(hb)
        except asyncio.CancelledError:
            pass


# --- CLI Entry Point ---

async def run_child(agent_id: str, role: str, router_addr: str):
    """子Agentをスタンドアロン起動"""
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{agent_id}] %(levelname)s: %(message)s",
    )

    child = ChildAgent(agent_id, role, router_addr)

    # Default task handler
    @child.on_message(MessageType.TASK_CREATE)
    async def handle_task(msg: AgentMessage):
        task_id = msg.payload.get("task_id")
        description = msg.payload.get("description", "")
        logger.info(f"Received task: {description}")

        # Think (AI stub)
        result_text = await child.think(description)
        logger.info(f"Task result:\n{result_text}")

        await child.complete_task(task_id, {"output": result_text})

    # Default DM handler
    @child.on_message(MessageType.AGENT_DM)
    async def handle_dm(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"DM from {msg.from_agent}: {content}")

    # Default broadcast handler
    @child.on_message(MessageType.AGENT_BROADCAST)
    async def handle_broadcast(msg: AgentMessage):
        content = msg.payload.get("content", "")
        logger.info(f"Broadcast from {msg.from_agent}: {content}")

    await child.start()

    try:
        while child.is_running:
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        await child.stop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ChildAgent DEALER client")
    parser.add_argument("--agent-id", default=os.environ.get("AGENT_ID", "child-1"))
    parser.add_argument("--role", default=os.environ.get("AGENT_ROLE", "worker"))
    parser.add_argument(
        "--router", default=os.environ.get("AGENT_ROUTER", "tcp://localhost:5570")
    )
    args = parser.parse_args()

    asyncio.run(run_child(args.agent_id, args.role, args.router))


if __name__ == "__main__":
    main()
