"""
Socket.IO ↔ ZMQ ブリッジ

フロントエンド（Socket.IO）とバックエンド（ZMQ）を双方向変換します。
フロントエンドは既存のSocket.IOプロトコルのまま変更不要。

Socket.IOイベント → AgentMessage → ZMQブローカー → Agent
Agent → ZMQブローカー → AgentMessage → Socket.IOイベント → フロントエンド
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from ..agent_protocol import AgentMessage, MessageType
from .zmq_broker import ZMQBroker
from .zmq_config import ZMQTopics

logger = logging.getLogger(__name__)


class SocketIOZMQBridge:
    """Socket.IO (フロントエンド) と ZMQ (バックエンド) を双方向変換"""

    def __init__(
        self,
        sio: Any,  # socketio.AsyncServer
        broker: ZMQBroker,
    ):
        self._sio = sio
        self._broker = broker
        self._running = False

        # Socket.IOセッション → ZMQマッピング
        self._session_agents: Dict[str, str] = {}  # session_id → agent_id

        # External command handlers (set by socket_handlers)
        self._command_inject_handler: Optional[Callable] = None
        self._command_propose_handler: Optional[Callable] = None

    def set_command_inject_handler(self, handler: Callable) -> None:
        """Set handler for COMMAND_INJECT messages from ZMQ agents"""
        self._command_inject_handler = handler

    def set_command_propose_handler(self, handler: Callable) -> None:
        """Set handler for COMMAND_PROPOSE messages from ZMQ agents"""
        self._command_propose_handler = handler

    async def start(self) -> None:
        """ブリッジを開始"""
        if self._running:
            return

        # ZMQブローカーのイベント購読
        self._broker.register_on_message(self._on_zmq_message)

        # Socket.IOイベントハンドラーを登録
        self._register_sio_handlers()

        self._running = True
        logger.info("Socket.IO ↔ ZMQ Bridge started")

    async def stop(self) -> None:
        """ブリッジを停止"""
        self._running = False
        logger.info("Socket.IO ↔ ZMQ Bridge stopped")

    def map_session_to_agent(self, session_id: str, agent_id: str) -> None:
        """ターミナルセッションとAgentのマッピングを設定"""
        self._session_agents[session_id] = agent_id
        logger.debug(f"Mapped session {session_id} → agent {agent_id}")

    def unmap_session(self, session_id: str) -> None:
        """マッピングを解除"""
        self._session_agents.pop(session_id, None)

    def _register_sio_handlers(self) -> None:
        """Socket.IOイベントハンドラーを登録"""

        @self._sio.on("agent_message")
        async def handle_agent_message(sid: str, data: dict) -> None:
            """フロントエンドからのAgentメッセージをZMQに転送"""
            try:
                message = AgentMessage.from_dict(data)
                to_agent = message.to_agent

                if to_agent:
                    await self._broker.send_to_agent(to_agent, message)
                    logger.debug(
                        f"SIO→ZMQ: {message.message_type.value} → {to_agent}"
                    )
            except Exception as e:
                logger.error(f"Error bridging SIO→ZMQ: {e}")

        @self._sio.on("agent_status_request")
        async def handle_status_request(sid: str, data: dict) -> None:
            """Agent状態リクエストを処理"""
            try:
                agents = self._broker.get_registered_agents()
                agent_list = [
                    {
                        "agent_id": reg.agent_id,
                        "capabilities": reg.capabilities,
                        "status": reg.status,
                    }
                    for reg in agents.values()
                ]

                await self._sio.emit(
                    "agent_status_response",
                    {"agents": agent_list},
                    room=sid,
                )
            except Exception as e:
                logger.error(f"Error handling status request: {e}")

    async def _on_zmq_message(self, message: AgentMessage) -> None:
        """ZMQブローカーからのメッセージをSocket.IOに転送"""
        if not self._running:
            return

        try:
            # Agent状態変更をフロントエンドに通知
            if message.message_type == MessageType.AGENT_REGISTER:
                await self._sio.emit(
                    "agent_status_update",
                    {
                        "agent_id": message.payload.get("agent_id"),
                        "status": "registered",
                        "capabilities": message.payload.get("capabilities", []),
                    },
                )

            elif message.message_type == MessageType.AGENT_UNREGISTER:
                await self._sio.emit(
                    "agent_status_update",
                    {
                        "agent_id": message.payload.get("agent_id"),
                        "status": "unregistered",
                    },
                )

            # コマンド提案: AgentShellからのCOMMAND_PROPOSEをフロントエンドに転送
            elif message.message_type == MessageType.COMMAND_PROPOSE:
                if self._command_propose_handler:
                    await self._command_propose_handler(message)
                else:
                    # Fallback: emit directly to Socket.IO
                    await self._sio.emit(
                        "command_proposed",
                        {
                            "from_agent": message.from_agent,
                            "command": message.payload.get("command", ""),
                            "description": message.payload.get("description", ""),
                            "require_approval": message.payload.get(
                                "require_approval", True
                            ),
                            "message_id": str(message.message_id),
                        },
                    )

            # コマンド注入: AgentShellからのCOMMAND_INJECTをターミナルPTYに書込み
            elif message.message_type == MessageType.COMMAND_INJECT:
                if self._command_inject_handler:
                    await self._command_inject_handler(message)
                else:
                    logger.warning(
                        "COMMAND_INJECT received but no handler registered"
                    )

        except Exception as e:
            logger.error(f"Error bridging ZMQ→SIO: {e}")

    async def forward_terminal_output_to_zmq(
        self, session_id: str, data: str
    ) -> None:
        """ターミナル出力をZMQ PUB/SUBで配信（全オブザーバーに配信）"""
        if not self._running:
            return

        msg = AgentMessage(
            from_agent=f"terminal_{session_id}",
            to_agent="",
            message_type=MessageType.TERMINAL_OUTPUT,
            payload={"session_id": session_id, "data": data},
        )
        topic = ZMQTopics.with_id(ZMQTopics.TERMINAL_OUTPUT, session_id)
        await self._broker.publish(topic, msg)

    async def forward_terminal_input_to_zmq(
        self, session_id: str, data: str
    ) -> None:
        """ターミナル入力をZMQ PUB/SUBで配信（全オブザーバーに配信）"""
        if not self._running:
            return

        msg = AgentMessage(
            from_agent=f"terminal_{session_id}",
            to_agent="",
            message_type=MessageType.TERMINAL_INPUT,
            payload={"session_id": session_id, "data": data},
        )
        topic = ZMQTopics.with_id(ZMQTopics.TERMINAL_INPUT, session_id)
        await self._broker.publish(topic, msg)

    @property
    def is_running(self) -> bool:
        return self._running
