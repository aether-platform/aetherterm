"""
ZMQエージェントクライアント基底クラス

全Agentが使うZMQクライアント。
DEALERソケットでブローカーと通信し、SUBソケットでイベントを受信します。
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional
from uuid import uuid4

import zmq
import zmq.asyncio

from ..agent_protocol import AgentMessage, MessageType
from .zmq_config import ZMQConfig, ZMQTopics
from .zmq_serializer import ZMQSerializer

logger = logging.getLogger(__name__)


class ZMQAgentClient:
    """全Agentが使うZMQクライアント基底"""

    def __init__(
        self,
        agent_id: str,
        config: ZMQConfig,
        capabilities: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.config = config
        self.capabilities = capabilities or []

        self._ctx: Optional[zmq.asyncio.Context] = None
        self._dealer: Optional[zmq.asyncio.Socket] = None
        self._sub: Optional[zmq.asyncio.Socket] = None
        self._connected = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._sub_task: Optional[asyncio.Task] = None
        self._message_handlers: Dict[
            MessageType, List[Callable[[AgentMessage], None]]
        ] = {}
        self._topic_handlers: Dict[str, List[Callable[[str, AgentMessage], None]]] = {}
        self._pending_replies: Dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """ブローカーに接続"""
        if self._connected:
            return

        self._ctx = zmq.asyncio.Context()

        # DEALER socket (RPC)
        self._dealer = self._ctx.socket(zmq.DEALER)
        self._dealer.identity = self.agent_id.encode("utf-8")
        self._dealer.setsockopt(zmq.SNDHWM, self.config.high_water_mark)
        self._dealer.setsockopt(zmq.RCVHWM, self.config.high_water_mark)
        self._dealer.setsockopt(zmq.SNDTIMEO, self.config.send_timeout)
        self._dealer.connect(self.config.broker_router_endpoint)

        # SUB socket (Events)
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(self.config.broker_pub_endpoint)

        self._connected = True
        self._sub_task = asyncio.create_task(self._sub_loop())

        logger.info(
            f"ZMQ Agent {self.agent_id} connected to broker "
            f"(DEALER={self.config.broker_router_endpoint}, "
            f"SUB={self.config.broker_pub_endpoint})"
        )

    async def disconnect(self) -> None:
        """ブローカーから切断"""
        self._connected = False

        # Heartbeat停止
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # SUBループ停止
        if self._sub_task and not self._sub_task.done():
            self._sub_task.cancel()
            try:
                await self._sub_task
            except asyncio.CancelledError:
                pass

        # Pending futuresをキャンセル
        for future in self._pending_replies.values():
            if not future.done():
                future.cancel()
        self._pending_replies.clear()

        # ソケットクローズ
        if self._dealer:
            self._dealer.close(linger=0)
            self._dealer = None
        if self._sub:
            self._sub.close(linger=0)
            self._sub = None
        if self._ctx:
            self._ctx.term()
            self._ctx = None

        logger.info(f"ZMQ Agent {self.agent_id} disconnected")

    async def send_message(
        self, msg: AgentMessage, timeout: Optional[float] = None
    ) -> Optional[AgentMessage]:
        """
        メッセージを送信（DEALER経由）

        Args:
            msg: 送信するメッセージ
            timeout: 応答待ちタイムアウト（秒）。Noneの場合は応答を待たない。

        Returns:
            応答メッセージ（timeoutが指定された場合）
        """
        if not self._connected or not self._dealer:
            logger.warning("Not connected, cannot send message")
            return None

        try:
            # DEALERフレーム: [b'', payload]
            payload = ZMQSerializer.serialize(msg)
            await self._dealer.send_multipart([b"", payload])

            if timeout is not None:
                # 応答を待つ
                correlation_id = str(msg.message_id)
                future: asyncio.Future = asyncio.get_event_loop().create_future()
                self._pending_replies[correlation_id] = future
                try:
                    return await asyncio.wait_for(future, timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Reply timeout for message {correlation_id}"
                    )
                    return None
                finally:
                    self._pending_replies.pop(correlation_id, None)

            return None

        except zmq.ZMQError as e:
            logger.error(f"ZMQ send error: {e}")
            return None

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[str, AgentMessage], None],
    ) -> None:
        """
        PUB/SUBトピックを購読

        Args:
            topic: トピックプレフィックス（例: "terminal.output.session123"）
            handler: (full_topic, message) を受け取るハンドラー
        """
        if not self._sub:
            logger.warning("SUB socket not initialized")
            return

        self._sub.subscribe(topic.encode("utf-8"))

        if topic not in self._topic_handlers:
            self._topic_handlers[topic] = []
        self._topic_handlers[topic].append(handler)

        logger.debug(f"Subscribed to topic: {topic}")

    async def unsubscribe(self, topic: str) -> None:
        """トピック購読を解除"""
        if self._sub:
            self._sub.unsubscribe(topic.encode("utf-8"))
        self._topic_handlers.pop(topic, None)

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None],
    ) -> None:
        """メッセージタイプ別ハンドラーを登録"""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        if handler not in self._message_handlers[message_type]:
            self._message_handlers[message_type].append(handler)

    def unregister_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None],
    ) -> None:
        """メッセージタイプ別ハンドラーを解除"""
        if message_type in self._message_handlers:
            handlers = self._message_handlers[message_type]
            if handler in handlers:
                handlers.remove(handler)

    async def register(self) -> bool:
        """
        ブローカーにAgent登録

        Returns:
            True if registration was acknowledged
        """
        msg = AgentMessage(
            from_agent=self.agent_id,
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={
                "agent_id": self.agent_id,
                "capabilities": self.capabilities,
            },
        )

        response = await self.send_message(msg, timeout=5.0)
        if response and response.message_type == MessageType.AGENT_REGISTER:
            logger.info(f"Agent {self.agent_id} registered with broker")
            return True

        logger.warning(f"Agent {self.agent_id} registration failed or timed out")
        return False

    async def start_heartbeat(self) -> None:
        """Heartbeatを開始"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.debug(
            f"Heartbeat started (interval={self.config.heartbeat_interval}s)"
        )

    async def _heartbeat_loop(self) -> None:
        """Heartbeat送信ループ"""
        try:
            while self._connected:
                msg = AgentMessage(
                    from_agent=self.agent_id,
                    to_agent="broker",
                    message_type=MessageType.AGENT_HEARTBEAT,
                    payload={"agent_id": self.agent_id},
                )
                await self.send_message(msg)
                await asyncio.sleep(self.config.heartbeat_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    async def _sub_loop(self) -> None:
        """SUBソケット受信ループ"""
        try:
            while self._connected and self._sub:
                try:
                    frames = await asyncio.wait_for(
                        self._sub.recv_multipart(), timeout=1.0
                    )
                    topic, message = ZMQSerializer.from_sub_frames(frames)
                    await self._dispatch_sub_message(topic, message)
                except asyncio.TimeoutError:
                    continue
                except zmq.ZMQError as e:
                    if self._connected:
                        logger.error(f"SUB recv error: {e}")
                    break
        except asyncio.CancelledError:
            pass

    async def _dispatch_sub_message(
        self, topic: str, message: AgentMessage
    ) -> None:
        """SUBメッセージをハンドラーにディスパッチ"""
        for registered_topic, handlers in self._topic_handlers.items():
            if topic.startswith(registered_topic):
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(topic, message)
                        else:
                            handler(topic, message)
                    except Exception as e:
                        logger.error(
                            f"SUB handler error for topic {topic}: {e}"
                        )

    async def _recv_dealer_loop(self) -> None:
        """DEALERソケット受信ループ（ブローカーからのメッセージ処理）"""
        try:
            while self._connected and self._dealer:
                try:
                    frames = await asyncio.wait_for(
                        self._dealer.recv_multipart(), timeout=1.0
                    )
                    # DEALER受信: [b'', payload]
                    if len(frames) >= 2:
                        message = ZMQSerializer.deserialize(frames[-1])
                        await self._dispatch_dealer_message(message)
                except asyncio.TimeoutError:
                    continue
                except zmq.ZMQError as e:
                    if self._connected:
                        logger.error(f"DEALER recv error: {e}")
                    break
        except asyncio.CancelledError:
            pass

    async def _dispatch_dealer_message(self, message: AgentMessage) -> None:
        """DEALERメッセージをハンドラーにディスパッチ"""
        # Reply待ちの場合
        reply_to = str(message.reply_to) if message.reply_to else None
        if reply_to and reply_to in self._pending_replies:
            future = self._pending_replies[reply_to]
            if not future.done():
                future.set_result(message)
            return

        # メッセージタイプ別ハンドラー
        handlers = self._message_handlers.get(message.message_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(
                    f"DEALER handler error for {message.message_type}: {e}"
                )

    async def start_recv_loop(self) -> None:
        """DEALER受信ループを開始（connectの後に呼び出す）"""
        asyncio.create_task(self._recv_dealer_loop())

    @property
    def is_connected(self) -> bool:
        return self._connected
