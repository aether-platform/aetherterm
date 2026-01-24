"""
ControlIntegration - AgentServerとControlServerの統合機能

ControlServerからの制御指示を受信し、セッション制御を実行
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.client import WebSocketClientProtocol

from .terminals.asyncio_terminal import AsyncioTerminal

logger = logging.getLogger(__name__)
class ControlIntegration:
    """ControlServer統合クラス"""

    def __init__(
        self, control_server_url: str = "ws://localhost:8765", agent_id: str = "agentserver_main"
    ):
        self.control_server_url = control_server_url
        self.agent_id = agent_id

        # WebSocket接続
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connection_task: Optional[asyncio.Task] = None
        self.listen_task: Optional[asyncio.Task] = None

        # 状態管理
        self.is_connected = False
        self.is_running = False
        self.blocked_sessions: Set[str] = set()

        # コールバック関数
        self.on_block_session: Optional[Callable] = None
        self.on_unblock_session: Optional[Callable] = None
        self.sio_instance = None

    def set_socketio_instance(self, sio):
        """Socket.IOインスタンスを設定"""
        self.sio_instance = sio

    def set_block_handlers(self, block_handler: Callable, unblock_handler: Callable):
        """ブロック/アンブロックハンドラーを設定"""
        self.on_block_session = block_handler
        self.on_unblock_session = unblock_handler

    async def start(self):
        """統合機能開始"""
        if self.is_running:
            logger.warning("ControlIntegration is already running")
            return

        self.is_running = True
        logger.info(f"Starting ControlIntegration with ControlServer: {self.control_server_url}")

        # ControlServerへの接続タスクを開始
        self.connection_task = asyncio.create_task(self._maintain_connection())

    async def stop(self):
        """統合機能停止"""
        if not self.is_running:
            return

        self.is_running = False
        logger.info("Stopping ControlIntegration")

        # タスクをキャンセル
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                pass

        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        # WebSocket接続を閉じる
        if self.websocket:
            await self.websocket.close()

    async def _maintain_connection(self):
        """ControlServerへの接続を維持"""
        while self.is_running:
            try:
                if not self.is_connected:
                    logger.info(f"Connecting to ControlServer: {self.control_server_url}")
                    self.websocket = await websockets.connect(f"{self.control_server_url}/agent")
                    self.is_connected = True
                    logger.info("Connected to ControlServer")

                    # AgentServer登録
                    await self._register_agent()

                    # メッセージ受信タスクを開始
                    self.listen_task = asyncio.create_task(self._listen_for_messages())

                # 接続が生きているかチェック
                if self.websocket.closed:
                    self.is_connected = False
                    logger.warning("ControlServer connection lost")

                await asyncio.sleep(5)  # 5秒間隔でチェック

            except Exception as e:
                self.is_connected = False
                logger.error(f"Error maintaining ControlServer connection: {e}")
                await asyncio.sleep(10)  # エラー時は10秒待機

    async def _register_agent(self):
        """AgentServerをControlServerに登録"""
        try:
            register_message = {
                "type": "agent_register",
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat(),
                "capabilities": ["session_control", "emergency_block"],
            }

            await self.websocket.send(json.dumps(register_message))
            logger.info(f"Sent agent registration: {self.agent_id}")

        except Exception as e:
            logger.error(f"Error registering agent: {e}")

    async def _listen_for_messages(self):
        """ControlServerからのメッセージを受信"""
        try:
            async for message in self.websocket:
                await self._handle_control_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("ControlServer connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error listening for messages: {e}")
            self.is_connected = False

    async def _handle_control_message(self, message: str):
        """制御メッセージを処理"""
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "emergency_block":
                await self._handle_emergency_block(data)
            elif message_type == "unblock_session":
                await self._handle_unblock_session(data)
            elif message_type == "registration_confirmed":
                logger.info("Registration confirmed by ControlServer")
            else:
                logger.debug(f"Received control message: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from ControlServer: {e}")
        except Exception as e:
            logger.error(f"Error handling control message: {e}")

    async def _handle_emergency_block(self, data: Dict):
        """緊急ブロック指示を処理"""
        block_id = data.get("block_id")
        action = data.get("action", "block_all_sessions")
        message = data.get("message", "緊急ブロック")
        affected_sessions = data.get("affected_sessions", [])

        logger.warning(f"Received emergency block: {block_id} - {message}")

        if action == "block_all_sessions":
            # 全セッションをブロック
            sessions_to_block = list(AsyncioTerminal.sessions.keys())
        elif action == "block_session":
            # 指定セッションのみブロック
            sessions_to_block = affected_sessions
        else:
            logger.warning(f"Unknown block action: {action}")
            return

        # セッションをブロック
        blocked_count = 0
        for session_id in sessions_to_block:
            if await self._block_session(session_id, message):
                self.blocked_sessions.add(session_id)
                blocked_count += 1

        logger.info(f"Blocked {blocked_count} sessions")

        # ControlServerに確認を送信
        await self._send_block_confirmation(block_id, list(self.blocked_sessions))

    async def _handle_unblock_session(self, data: Dict):
        """セッションブロック解除を処理"""
        session_id = data.get("session_id")
        admin_user = data.get("admin_user")

        if session_id in self.blocked_sessions:
            if await self._unblock_session(session_id):
                self.blocked_sessions.remove(session_id)
                logger.info(f"Unblocked session {session_id} by {admin_user}")
            else:
                logger.error(f"Failed to unblock session {session_id}")
        else:
            logger.warning(f"Session {session_id} is not blocked")

    async def _block_session(self, session_id: str, message: str) -> bool:
        """セッションをブロック"""
        try:
            if session_id not in AsyncioTerminal.sessions:
                logger.warning(f"Session {session_id} not found for blocking")
                return False

            terminal = AsyncioTerminal.sessions[session_id]

            # Socket.IOクライアントにブロック通知を送信
            if self.sio_instance and hasattr(terminal, "client_sids"):
                for client_sid in terminal.client_sids:
                    await self.sio_instance.emit(
                        "input_block",
                        {
                            "message": f"!!!CRITICAL ALERT!!! {message}",
                            "block_reason": message,
                            "unblock_key": "Ctrl+D",
                            "session_id": session_id,
                        },
                        room=client_sid,
                    )

            logger.info(f"Blocked session {session_id}: {message}")
            return True

        except Exception as e:
            logger.error(f"Error blocking session {session_id}: {e}")
            return False

    async def _unblock_session(self, session_id: str) -> bool:
        """セッションのブロックを解除"""
        try:
            if session_id not in AsyncioTerminal.sessions:
                logger.warning(f"Session {session_id} not found for unblocking")
                return False

            terminal = AsyncioTerminal.sessions[session_id]

            # Socket.IOクライアントにブロック解除通知を送信
            if self.sio_instance and hasattr(terminal, "client_sids"):
                for client_sid in terminal.client_sids:
                    await self.sio_instance.emit(
                        "input_unblock",
                        {"message": "ブロックが解除されました", "session_id": session_id},
                        room=client_sid,
                    )

            logger.info(f"Unblocked session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error unblocking session {session_id}: {e}")
            return False

    async def _send_block_confirmation(self, block_id: str, confirmed_sessions: List[str]):
        """ブロック確認をControlServerに送信"""
        try:
            confirmation = {
                "type": "block_confirmation",
                "block_id": block_id,
                "agent_id": self.agent_id,
                "confirmed_sessions": confirmed_sessions,
                "timestamp": datetime.now().isoformat(),
            }

            await self.websocket.send(json.dumps(confirmation))
            logger.debug(f"Sent block confirmation: {block_id}")

        except Exception as e:
            logger.error(f"Error sending block confirmation: {e}")

    async def send_session_update(self, session_id: str, session_data: Dict):
        """セッション更新をControlServerに送信"""
        if not self.is_connected or not self.websocket:
            return

        try:
            update_message = {
                "type": "session_update",
                "agent_id": self.agent_id,
                "session": {
                    "session_id": session_id,
                    "user_info": session_data.get("user_info", {}),
                    "created_at": session_data.get("created_at", datetime.now().isoformat()),
                    "last_activity": datetime.now().isoformat(),
                },
                "timestamp": datetime.now().isoformat(),
            }

            await self.websocket.send(json.dumps(update_message))
            logger.debug(f"Sent session update: {session_id}")

        except Exception as e:
            logger.error(f"Error sending session update: {e}")

    async def send_unblock_request(self, session_id: str, user_action: str = "ctrl_d"):
        """ブロック解除要求をControlServerに送信"""
        if not self.is_connected or not self.websocket:
            return

        try:
            request_message = {
                "type": "unblock_request",
                "agent_id": self.agent_id,
                "session_id": session_id,
                "user_action": user_action,
                "timestamp": datetime.now().isoformat(),
            }

            await self.websocket.send(json.dumps(request_message))
            logger.info(f"Sent unblock request: {session_id}")

        except Exception as e:
            logger.error(f"Error sending unblock request: {e}")

    def is_session_blocked(self, session_id: str) -> bool:
        """セッションがブロックされているかチェック"""
        return session_id in self.blocked_sessions

    def get_status(self) -> Dict:
        """統合機能の状態を取得"""
        return {
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "control_server_url": self.control_server_url,
            "agent_id": self.agent_id,
            "blocked_sessions_count": len(self.blocked_sessions),
            "blocked_sessions": list(self.blocked_sessions),
        }
