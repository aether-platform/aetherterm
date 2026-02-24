"""
ZMQ AgentConnector

Socket.IOベースのServerConnectorのZMQ版。
同じインターフェースを提供し、AgentOrchestrator/AgentCoordinatorから透過的に利用可能。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..common.agent_protocol import AgentMessage, MessageType
from ..common.zmq.zmq_client import ZMQAgentClient
from ..common.zmq.zmq_config import ZMQConfig

logger = logging.getLogger(__name__)


class ZMQAgentConnector:
    """
    ZMQベースのAgent通信コネクター

    ServerConnectorと同じインターフェースを持ち、
    ZMQ DEALER/SUBソケットでブローカーと通信します。
    """

    def __init__(
        self,
        agent_id: str,
        zmq_config: ZMQConfig,
        capabilities: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.session_id: str = "default"

        self._zmq_client = ZMQAgentClient(
            agent_id=agent_id,
            config=zmq_config,
            capabilities=capabilities or [],
        )
        self._message_handlers: Dict[MessageType, List[Callable[[AgentMessage], None]]] = {}
        self._sync_callbacks: List[Callable] = []
        self._is_enabled = False

    async def start(self) -> bool:
        """
        ZMQ接続を開始

        Returns:
            bool: 接続に成功した場合True
        """
        try:
            await self._zmq_client.connect()
            registered = await self._zmq_client.register()

            if registered:
                await self._zmq_client.start_heartbeat()
                await self._zmq_client.start_recv_loop()
                self._is_enabled = True

                # メッセージハンドラーをZMQクライアントに転送
                for msg_type, handlers in self._message_handlers.items():
                    for handler in handlers:
                        self._zmq_client.register_handler(msg_type, handler)

                logger.info(f"ZMQAgentConnector started: {self.agent_id}")

                # 同期コールバックを実行
                for callback in self._sync_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback("connected")
                        else:
                            callback("connected")
                    except Exception as e:
                        logger.error(f"Sync callback error: {e}")

                return True

            logger.warning("ZMQ registration failed")
            return False

        except Exception as e:
            logger.error(f"ZMQAgentConnector start failed: {e}")
            return False

    async def stop(self) -> None:
        """ZMQ接続を停止"""
        self._is_enabled = False

        # Unregister
        unregister_msg = AgentMessage(
            from_agent=self.agent_id,
            to_agent="broker",
            message_type=MessageType.AGENT_UNREGISTER,
            payload={"agent_id": self.agent_id},
        )
        await self._zmq_client.send_message(unregister_msg)

        await self._zmq_client.disconnect()

        # 同期コールバックを実行
        for callback in self._sync_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback("disconnected")
                else:
                    callback("disconnected")
            except Exception as e:
                logger.error(f"Sync callback error: {e}")

        logger.info(f"ZMQAgentConnector stopped: {self.agent_id}")

    async def send_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        エージェントメッセージを送信

        Args:
            message: 送信するメッセージ

        Returns:
            Optional[AgentMessage]: 応答メッセージ
        """
        if not self.is_connected():
            logger.warning("Not connected, cannot send message")
            return None

        return await self._zmq_client.send_message(message, timeout=5.0)

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None],
    ) -> None:
        """メッセージハンドラーを登録"""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []

        if handler not in self._message_handlers[message_type]:
            self._message_handlers[message_type].append(handler)

            # 既に接続中の場合はZMQクライアントにも登録
            if self._is_enabled:
                self._zmq_client.register_handler(message_type, handler)

    def unregister_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None],
    ) -> None:
        """メッセージハンドラーを解除"""
        if message_type in self._message_handlers:
            handlers = self._message_handlers[message_type]
            if handler in handlers:
                handlers.remove(handler)

            if self._is_enabled:
                self._zmq_client.unregister_handler(message_type, handler)

    def register_sync_callback(self, callback: Callable) -> None:
        """同期コールバックを登録"""
        if callback not in self._sync_callbacks:
            self._sync_callbacks.append(callback)

    def unregister_sync_callback(self, callback: Callable) -> None:
        """同期コールバックを解除"""
        if callback in self._sync_callbacks:
            self._sync_callbacks.remove(callback)

    def is_connected(self) -> bool:
        """接続状態を確認"""
        return self._is_enabled and self._zmq_client.is_connected

    def is_enabled(self) -> bool:
        """連携が有効かどうかを確認"""
        return self._is_enabled

    def get_status(self) -> Dict[str, Any]:
        """連携状態を取得"""
        return {
            "enabled": self._is_enabled,
            "connected": self.is_connected(),
            "agent_id": self.agent_id,
            "transport": "zmq",
        }

    async def subscribe_topic(
        self,
        topic: str,
        handler: Callable,
    ) -> None:
        """PUB/SUBトピックを購読"""
        await self._zmq_client.subscribe(topic, handler)

    async def unsubscribe_topic(self, topic: str) -> None:
        """トピック購読を解除"""
        await self._zmq_client.unsubscribe(topic)
