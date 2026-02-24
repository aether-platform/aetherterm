"""
ZMQブローカー

AgentServer内で起動する中央メッセージブローカー。
ROUTER/DEALERパターンでRPCルーティング、PUB/SUBでイベントブロードキャスト、
PUSH/PULLでタスク分配を行います。

Agent Registry でAgent登録・Heartbeat死活監視を管理します。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

import zmq
import zmq.asyncio

from ..agent_protocol import AgentMessage, MessageType
from .zmq_config import ZMQConfig, ZMQTopics
from .zmq_serializer import ZMQSerializer

logger = logging.getLogger(__name__)


@dataclass
class AgentRegistration:
    """登録されたAgentの情報"""

    agent_id: str
    identity: bytes  # ZMQ ROUTER identity
    capabilities: List[str] = field(default_factory=list)
    last_heartbeat: float = field(default_factory=time.time)
    registered_at: float = field(default_factory=time.time)
    status: str = "active"  # active, stale, dead


class ZMQBroker:
    """
    AgentServer内で起動する中央メッセージブローカー

    - ROUTER (port 5560): Agent登録、RPC、メッセージルーティング
    - PUB (port 5561): イベントブロードキャスト
    - PUSH (port 5562): タスク分配
    - Agent Registry: {agent_id: AgentRegistration}
    - Heartbeat Monitor: heartbeat_timeout秒でAgent死亡判定
    """

    def __init__(self, config: ZMQConfig):
        self.config = config

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._router: Optional[zmq.asyncio.Socket] = None
        self._pub: Optional[zmq.asyncio.Socket] = None
        self._push: Optional[zmq.asyncio.Socket] = None

        self._registry: Dict[str, AgentRegistration] = {}
        self._identity_to_agent: Dict[bytes, str] = {}

        self._running = False
        self._router_task: Optional[asyncio.Task] = None
        self._heartbeat_monitor_task: Optional[asyncio.Task] = None

        # コールバック
        self._on_agent_registered: List[Callable[[AgentRegistration], None]] = []
        self._on_agent_removed: List[Callable[[str], None]] = []
        self._on_message: List[Callable[[AgentMessage], None]] = []

    async def start(self) -> None:
        """ブローカーを起動"""
        if self._running:
            return

        self._ctx = zmq.asyncio.Context()

        # ROUTER socket
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.setsockopt(zmq.SNDHWM, self.config.high_water_mark)
        self._router.setsockopt(zmq.RCVHWM, self.config.high_water_mark)
        self._router.bind(self.config.broker_router_endpoint)

        # PUB socket
        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.setsockopt(zmq.SNDHWM, self.config.high_water_mark)
        self._pub.bind(self.config.broker_pub_endpoint)

        # PUSH socket
        self._push = self._ctx.socket(zmq.PUSH)
        self._push.setsockopt(zmq.SNDHWM, self.config.high_water_mark)
        self._push.bind(self.config.broker_push_endpoint)

        self._running = True
        self._router_task = asyncio.create_task(self._router_loop())
        self._heartbeat_monitor_task = asyncio.create_task(
            self._heartbeat_monitor_loop()
        )

        logger.info(
            f"ZMQ Broker started "
            f"(ROUTER={self.config.broker_router_endpoint}, "
            f"PUB={self.config.broker_pub_endpoint}, "
            f"PUSH={self.config.broker_push_endpoint})"
        )

    async def stop(self) -> None:
        """ブローカーを停止"""
        self._running = False

        # タスク停止
        for task in [self._router_task, self._heartbeat_monitor_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # ソケットクローズ
        for sock in [self._router, self._pub, self._push]:
            if sock:
                sock.close(linger=0)

        if self._ctx:
            self._ctx.term()
            self._ctx = None

        self._registry.clear()
        self._identity_to_agent.clear()

        logger.info("ZMQ Broker stopped")

    async def publish(self, topic: str, message: AgentMessage) -> None:
        """PUBソケットでイベントを配信"""
        if not self._pub:
            return

        try:
            frames = ZMQSerializer.to_pub_frames(topic, message)
            await self._pub.send_multipart(frames)
            logger.debug(f"Published to {topic}")
        except zmq.ZMQError as e:
            logger.error(f"Publish error on topic {topic}: {e}")

    async def send_to_agent(
        self, agent_id: str, message: AgentMessage
    ) -> bool:
        """特定のAgentにメッセージを送信（ROUTER経由）"""
        reg = self._registry.get(agent_id)
        if not reg or not self._router:
            logger.warning(f"Agent {agent_id} not found in registry")
            return False

        try:
            frames = ZMQSerializer.to_router_frames(reg.identity, message)
            await self._router.send_multipart(frames)
            return True
        except zmq.ZMQError as e:
            logger.error(f"Send to agent {agent_id} error: {e}")
            return False

    def get_registered_agents(self) -> Dict[str, AgentRegistration]:
        """登録されたAgentの一覧を取得"""
        return self._registry.copy()

    def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        """特定のAgentの登録情報を取得"""
        return self._registry.get(agent_id)

    def find_agents_by_capability(
        self, capability: str
    ) -> List[AgentRegistration]:
        """特定のcapabilityを持つAgentを検索"""
        return [
            reg
            for reg in self._registry.values()
            if capability in reg.capabilities and reg.status == "active"
        ]

    def register_on_agent_registered(
        self, callback: Callable[[AgentRegistration], None]
    ) -> None:
        """Agent登録時のコールバックを登録"""
        self._on_agent_registered.append(callback)

    def register_on_agent_removed(
        self, callback: Callable[[str], None]
    ) -> None:
        """Agent削除時のコールバックを登録"""
        self._on_agent_removed.append(callback)

    def register_on_message(
        self, callback: Callable[[AgentMessage], None]
    ) -> None:
        """全メッセージ受信時のコールバックを登録"""
        self._on_message.append(callback)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def agent_count(self) -> int:
        return len(self._registry)

    # ---- Internal ----

    async def _router_loop(self) -> None:
        """ROUTERソケットのメッセージ受信ループ"""
        try:
            while self._running and self._router:
                try:
                    frames = await asyncio.wait_for(
                        self._router.recv_multipart(), timeout=1.0
                    )
                    await self._handle_router_message(frames)
                except asyncio.TimeoutError:
                    continue
                except zmq.ZMQError as e:
                    if self._running:
                        logger.error(f"ROUTER recv error: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Router loop error: {e}")

    async def _handle_router_message(self, frames: List[bytes]) -> None:
        """ROUTERフレームを処理"""
        if len(frames) < 3:
            logger.warning(f"Invalid ROUTER frame: {len(frames)} parts")
            return

        identity = frames[0]
        # frames[1] == b'' (delimiter)
        payload = frames[2]

        try:
            message = ZMQSerializer.deserialize(payload)
        except Exception as e:
            logger.error(f"Deserialize error: {e}")
            return

        # コールバック通知
        for callback in self._on_message:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"on_message callback error: {e}")

        # メッセージタイプ別処理
        if message.message_type == MessageType.AGENT_REGISTER:
            await self._handle_register(identity, message)
        elif message.message_type == MessageType.AGENT_UNREGISTER:
            await self._handle_unregister(identity, message)
        elif message.message_type == MessageType.AGENT_HEARTBEAT:
            self._handle_heartbeat(identity, message)
        else:
            await self._route_message(identity, message)

    async def _handle_register(
        self, identity: bytes, message: AgentMessage
    ) -> None:
        """Agent登録を処理"""
        agent_id = message.payload.get("agent_id", message.from_agent)
        capabilities = message.payload.get("capabilities", [])

        reg = AgentRegistration(
            agent_id=agent_id,
            identity=identity,
            capabilities=capabilities,
        )

        self._registry[agent_id] = reg
        self._identity_to_agent[identity] = agent_id

        logger.info(
            f"Agent registered: {agent_id} "
            f"(capabilities={capabilities})"
        )

        # ACK応答を送信
        ack = AgentMessage(
            from_agent="broker",
            to_agent=agent_id,
            message_type=MessageType.AGENT_REGISTER,
            payload={"status": "registered", "agent_id": agent_id},
            reply_to=message.message_id,
        )

        try:
            frames = ZMQSerializer.to_router_frames(identity, ack)
            await self._router.send_multipart(frames)
        except zmq.ZMQError as e:
            logger.error(f"Register ACK send error: {e}")

        # コールバック通知
        for callback in self._on_agent_registered:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reg)
                else:
                    callback(reg)
            except Exception as e:
                logger.error(f"on_agent_registered callback error: {e}")

    async def _handle_unregister(
        self, identity: bytes, message: AgentMessage
    ) -> None:
        """Agent登録解除を処理"""
        agent_id = message.payload.get("agent_id", message.from_agent)
        self._remove_agent(agent_id)

    def _handle_heartbeat(
        self, identity: bytes, message: AgentMessage
    ) -> None:
        """Heartbeatを処理"""
        agent_id = message.payload.get("agent_id", message.from_agent)
        reg = self._registry.get(agent_id)

        if reg:
            reg.last_heartbeat = time.time()
            if reg.status == "stale":
                reg.status = "active"
                logger.info(f"Agent {agent_id} recovered from stale state")
        else:
            # 未登録のAgentからのheartbeat → identityを記録しておく
            logger.debug(
                f"Heartbeat from unregistered agent: {agent_id}"
            )

    async def _route_message(
        self, sender_identity: bytes, message: AgentMessage
    ) -> None:
        """メッセージを宛先Agentにルーティング"""
        to_agent = message.to_agent

        if not to_agent or to_agent == "broker":
            # ブローカー宛 or 宛先なし → 無視
            logger.debug(
                f"Message from {message.from_agent} to broker (ignored routing)"
            )
            return

        # 宛先Agentを検索
        target = self._registry.get(to_agent)
        if not target:
            logger.warning(
                f"Routing failed: agent {to_agent} not found "
                f"(from {message.from_agent})"
            )
            return

        # 転送
        try:
            frames = ZMQSerializer.to_router_frames(target.identity, message)
            await self._router.send_multipart(frames)
            logger.debug(
                f"Routed message: {message.from_agent} -> {to_agent} "
                f"({message.message_type.value})"
            )
        except zmq.ZMQError as e:
            logger.error(
                f"Route error {message.from_agent} -> {to_agent}: {e}"
            )

    async def _heartbeat_monitor_loop(self) -> None:
        """Heartbeatタイムアウト監視ループ"""
        try:
            while self._running:
                await asyncio.sleep(self.config.heartbeat_interval)
                now = time.time()
                stale_agents = []

                for agent_id, reg in self._registry.items():
                    elapsed = now - reg.last_heartbeat

                    if elapsed > self.config.heartbeat_timeout:
                        if reg.status == "active":
                            reg.status = "stale"
                            logger.warning(
                                f"Agent {agent_id} is stale "
                                f"(no heartbeat for {elapsed:.0f}s)"
                            )
                        elif reg.status == "stale":
                            # 2回連続stale → dead → 削除
                            stale_agents.append(agent_id)

                for agent_id in stale_agents:
                    logger.warning(f"Removing dead agent: {agent_id}")
                    self._remove_agent(agent_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat monitor error: {e}")

    def _remove_agent(self, agent_id: str) -> None:
        """Agentをレジストリから削除"""
        reg = self._registry.pop(agent_id, None)
        if reg:
            self._identity_to_agent.pop(reg.identity, None)
            logger.info(f"Agent removed: {agent_id}")

            # コールバック通知
            for callback in self._on_agent_removed:
                try:
                    callback(agent_id)
                except Exception as e:
                    logger.error(f"on_agent_removed callback error: {e}")
