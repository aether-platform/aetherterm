"""
CentralController - 中央制御システム

管理者からの制御指示を受信し、全AgentServerに一括指示を送信
"""

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from .log_summary_manager import LogSummaryManager

logger = logging.getLogger(__name__)
@dataclass
class BlockCommand:
    """ブロックコマンド"""

    block_id: str
    block_type: str  # "admin_initiated", "auto_detected", "emergency"
    reason: str
    admin_user: Optional[str]
    affected_sessions: List[str]
    timestamp: str
    expires_at: Optional[str] = None
@dataclass
class SessionInfo:
    """セッション情報"""

    session_id: str
    agent_server_id: str
    user_info: Dict
    created_at: str
    last_activity: str
    is_blocked: bool = False
    block_reason: Optional[str] = None
class CentralController:
    """中央制御システム"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port

        # 接続管理
        self.agent_servers: Dict[str, WebSocketServerProtocol] = {}
        self.admin_clients: Set[WebSocketServerProtocol] = set()

        # 状態管理
        self.active_sessions: Dict[str, SessionInfo] = {}
        self.active_blocks: Dict[str, BlockCommand] = {}
        self.block_history: List[BlockCommand] = []

        # WebSocketサーバー
        self.server = None

        # ログサマリ管理
        self.log_summary_manager = LogSummaryManager()

    async def start(self):
        """中央制御サーバー開始"""
        logger.info(f"Starting CentralController on {self.host}:{self.port}")

        self.server = await websockets.serve(self.handle_connection, self.host, self.port)

        # ログサマリ管理開始
        await self.log_summary_manager.start()

        logger.info(f"CentralController started on ws://{self.host}:{self.port}")

    async def stop(self):
        """中央制御サーバー停止"""
        # ログサマリ管理停止
        await self.log_summary_manager.stop()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # 全接続を閉じる
        all_connections = list(self.agent_servers.values()) + list(self.admin_clients)
        if all_connections:
            await asyncio.gather(*[ws.close() for ws in all_connections], return_exceptions=True)

        logger.info("CentralController stopped")

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """WebSocket接続ハンドラー"""
        client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"New connection from {client_addr} on path {path}")

        try:
            # パスに基づいて接続タイプを判定
            if path.startswith("/admin"):
                await self.handle_admin_connection(websocket)
            elif path.startswith("/agent"):
                await self.handle_agent_connection(websocket)
            else:
                # デフォルトはAgentServer接続として扱う
                await self.handle_agent_connection(websocket)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling connection {client_addr}: {e}")
        finally:
            # 接続を削除
            self._remove_connection(websocket)

    async def handle_admin_connection(self, websocket: WebSocketServerProtocol):
        """管理者接続ハンドラー"""
        self.admin_clients.add(websocket)
        logger.info("Admin client connected")

        # 現在の状態を送信
        await self.send_current_status(websocket)

        async for message in websocket:
            await self.handle_admin_message(websocket, message)

    async def handle_agent_connection(self, websocket: WebSocketServerProtocol):
        """AgentServer接続ハンドラー"""
        agent_id = None

        async for message in websocket:
            try:
                data = json.loads(message)

                # 初回接続時にAgentServer IDを登録
                if data.get("type") == "agent_register":
                    agent_id = data.get("agent_id", f"agent_{len(self.agent_servers)}")
                    self.agent_servers[agent_id] = websocket
                    logger.info(f"AgentServer registered: {agent_id}")

                    # 登録確認を送信
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "registration_confirmed",
                                "agent_id": agent_id,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )

                await self.handle_agent_message(websocket, data, agent_id)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from agent: {e}")
            except Exception as e:
                logger.error(f"Error handling agent message: {e}")

        # 接続終了時にAgentServerを削除
        if agent_id and agent_id in self.agent_servers:
            del self.agent_servers[agent_id]
            logger.info(f"AgentServer disconnected: {agent_id}")

    async def handle_admin_message(self, websocket: WebSocketServerProtocol, message: str):
        """管理者メッセージハンドラー"""
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "block_all_sessions":
                await self.execute_block_all(data)
            elif message_type == "block_session":
                await self.execute_block_session(data)
            elif message_type == "unblock_session":
                await self.execute_unblock_session(data)
            elif message_type == "get_status":
                await self.send_current_status(websocket)
            elif message_type == "get_block_history":
                await self.send_block_history(websocket)
            elif message_type == "get_log_summaries":
                await self.send_log_summaries(websocket, data)
            elif message_type == "get_memory_statistics":
                await self.send_memory_statistics(websocket)
            else:
                logger.warning(f"Unknown admin message type: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from admin: {e}")
        except Exception as e:
            logger.error(f"Error handling admin message: {e}")

    async def handle_agent_message(
        self, websocket: WebSocketServerProtocol, data: Dict, agent_id: str
    ):
        """AgentServerメッセージハンドラー"""
        message_type = data.get("type")

        if message_type == "session_update":
            await self.update_session_info(data, agent_id)
        elif message_type == "block_confirmation":
            await self.handle_block_confirmation(data, agent_id)
        elif message_type == "unblock_request":
            await self.handle_unblock_request(data, agent_id)
        elif message_type == "short_term_memory":
            await self.handle_short_term_memory(data, agent_id)
        else:
            logger.debug(f"Received message from {agent_id}: {message_type}")

    async def execute_block_all(self, data: Dict):
        """全セッション一括ブロック実行"""
        block_id = str(uuid.uuid4())
        reason = data.get("reason", "管理者による緊急ブロック")
        admin_user = data.get("admin_user")

        block_command = BlockCommand(
            block_id=block_id,
            block_type="admin_initiated",
            reason=reason,
            admin_user=admin_user,
            affected_sessions=list(self.active_sessions.keys()),
            timestamp=datetime.now().isoformat(),
        )

        # ブロックコマンドを記録
        self.active_blocks[block_id] = block_command
        self.block_history.append(block_command)

        logger.warning(f"Executing block all sessions: {reason} (ID: {block_id})")

        # 全AgentServerに一括ブロック指示を送信
        block_message = {
            "type": "emergency_block",
            "block_id": block_id,
            "severity": "admin_initiated",
            "message": f"管理者による緊急ブロック: {reason}",
            "action": "block_all_sessions",
            "affected_sessions": block_command.affected_sessions,
            "timestamp": block_command.timestamp,
        }

        await self.broadcast_to_agents(block_message)

        # 管理者クライアントに実行確認を送信
        await self.broadcast_to_admins(
            {"type": "block_executed", "block_command": asdict(block_command)}
        )

    async def execute_block_session(self, data: Dict):
        """個別セッションブロック実行"""
        session_id = data.get("session_id")
        reason = data.get("reason", "管理者による個別ブロック")
        admin_user = data.get("admin_user")

        if session_id not in self.active_sessions:
            logger.warning(f"Session not found for blocking: {session_id}")
            return

        block_id = str(uuid.uuid4())
        block_command = BlockCommand(
            block_id=block_id,
            block_type="admin_initiated",
            reason=reason,
            admin_user=admin_user,
            affected_sessions=[session_id],
            timestamp=datetime.now().isoformat(),
        )

        self.active_blocks[block_id] = block_command
        self.block_history.append(block_command)

        # 該当AgentServerに個別ブロック指示を送信
        session_info = self.active_sessions[session_id]
        agent_id = session_info.agent_server_id

        if agent_id in self.agent_servers:
            block_message = {
                "type": "emergency_block",
                "block_id": block_id,
                "severity": "admin_initiated",
                "message": f"管理者による個別ブロック: {reason}",
                "action": "block_session",
                "affected_sessions": [session_id],
                "timestamp": block_command.timestamp,
            }

            await self.agent_servers[agent_id].send(json.dumps(block_message))

        logger.info(f"Executed block session {session_id}: {reason}")

    async def execute_unblock_session(self, data: Dict):
        """セッションブロック解除実行"""
        session_id = data.get("session_id")
        admin_user = data.get("admin_user")

        # アクティブなブロックを検索
        block_to_remove = None
        for block_id, block_cmd in self.active_blocks.items():
            if session_id in block_cmd.affected_sessions:
                block_to_remove = block_id
                break

        if not block_to_remove:
            logger.warning(f"No active block found for session: {session_id}")
            return

        # ブロックを削除
        del self.active_blocks[block_to_remove]

        # 該当AgentServerにブロック解除指示を送信
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            agent_id = session_info.agent_server_id

            if agent_id in self.agent_servers:
                unblock_message = {
                    "type": "unblock_session",
                    "session_id": session_id,
                    "admin_user": admin_user,
                    "timestamp": datetime.now().isoformat(),
                }

                await self.agent_servers[agent_id].send(json.dumps(unblock_message))

        logger.info(f"Executed unblock session {session_id} by {admin_user}")

    async def update_session_info(self, data: Dict, agent_id: str):
        """セッション情報更新"""
        session_data = data.get("session", {})
        session_id = session_data.get("session_id")

        if not session_id:
            return

        session_info = SessionInfo(
            session_id=session_id,
            agent_server_id=agent_id,
            user_info=session_data.get("user_info", {}),
            created_at=session_data.get("created_at", datetime.now().isoformat()),
            last_activity=datetime.now().isoformat(),
        )

        self.active_sessions[session_id] = session_info

    async def broadcast_to_agents(self, message: Dict):
        """全AgentServerに一括送信"""
        if not self.agent_servers:
            logger.warning("No AgentServers connected for broadcast")
            return

        message_json = json.dumps(message)

        # 全AgentServerに並行送信
        tasks = []
        for agent_id, websocket in self.agent_servers.items():
            tasks.append(self.safe_send(websocket, message_json, agent_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 送信結果をログ出力
        success_count = sum(1 for r in results if r is True)
        logger.info(f"Broadcast sent to {success_count}/{len(tasks)} AgentServers")

    async def broadcast_to_admins(self, message: Dict):
        """全管理者クライアントに一括送信"""
        if not self.admin_clients:
            return

        message_json = json.dumps(message)

        tasks = []
        for websocket in self.admin_clients.copy():
            tasks.append(self.safe_send(websocket, message_json, "admin"))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def safe_send(
        self, websocket: WebSocketServerProtocol, message: str, client_id: str
    ) -> bool:
        """安全なメッセージ送信"""
        try:
            await websocket.send(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {client_id}: {e}")
            # 接続が切れている場合は削除
            self._remove_connection(websocket)
            return False

    def _remove_connection(self, websocket: WebSocketServerProtocol):
        """接続を削除"""
        # AgentServerから削除
        agent_to_remove = None
        for agent_id, ws in self.agent_servers.items():
            if ws == websocket:
                agent_to_remove = agent_id
                break
        if agent_to_remove:
            del self.agent_servers[agent_to_remove]

        # 管理者クライアントから削除
        self.admin_clients.discard(websocket)

    async def send_current_status(self, websocket: WebSocketServerProtocol):
        """現在の状態を送信"""
        status = {
            "type": "current_status",
            "timestamp": datetime.now().isoformat(),
            "agent_servers": len(self.agent_servers),
            "active_sessions": len(self.active_sessions),
            "active_blocks": len(self.active_blocks),
            "sessions": [asdict(session) for session in self.active_sessions.values()],
            "blocks": [asdict(block) for block in self.active_blocks.values()],
        }

        await websocket.send(json.dumps(status))

    async def send_block_history(self, websocket: WebSocketServerProtocol):
        """ブロック履歴を送信"""
        history = {
            "type": "block_history",
            "timestamp": datetime.now().isoformat(),
            "total_blocks": len(self.block_history),
            "history": [asdict(block) for block in self.block_history[-50:]],  # 最新50件
        }

        await websocket.send(json.dumps(history))

    async def handle_block_confirmation(self, data: Dict, agent_id: str):
        """ブロック確認処理"""
        block_id = data.get("block_id")
        confirmed_sessions = data.get("confirmed_sessions", [])

        logger.info(
            f"Block confirmation from {agent_id}: {block_id}, sessions: {len(confirmed_sessions)}"
        )

        # 管理者クライアントに確認を通知
        await self.broadcast_to_admins(
            {
                "type": "block_confirmation",
                "block_id": block_id,
                "agent_id": agent_id,
                "confirmed_sessions": confirmed_sessions,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_unblock_request(self, data: Dict, agent_id: str):
        """ブロック解除要求処理"""
        session_id = data.get("session_id")
        user_action = data.get("user_action", "unknown")

        logger.info(f"Unblock request from {agent_id}: session {session_id}, action: {user_action}")

        # Ctrl+Dによる解除の場合は自動承認
        if user_action == "ctrl_d":
            await self.execute_unblock_session(
                {"session_id": session_id, "admin_user": "system_auto_unblock"}
            )

        # 管理者クライアントに解除要求を通知
        await self.broadcast_to_admins(
            {
                "type": "unblock_request",
                "session_id": session_id,
                "agent_id": agent_id,
                "user_action": user_action,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_short_term_memory(self, data: Dict, agent_id: str):
        """AgentServerからの短期記憶データを処理"""
        try:
            # エージェントIDを追加してログサマリマネージャーに送信
            memory_data = data.get("memory", {})
            memory_data["agent_id"] = agent_id

            await self.log_summary_manager.receive_short_term_memory(memory_data)

            logger.debug(
                f"Received short-term memory from {agent_id}: {memory_data.get('memory_type')}"
            )

        except Exception as e:
            logger.error(f"Error processing short-term memory from {agent_id}: {e}")

    async def send_log_summaries(self, websocket: WebSocketServerProtocol, data: Dict):
        """ログサマリを送信"""
        try:
            limit = data.get("limit", 10)
            summaries = self.log_summary_manager.get_recent_summaries(limit)

            response = {
                "type": "log_summaries",
                "timestamp": datetime.now().isoformat(),
                "summaries": summaries,
                "total_count": len(summaries),
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error sending log summaries: {e}")

    async def send_memory_statistics(self, websocket: WebSocketServerProtocol):
        """メモリ統計を送信"""
        try:
            stats = self.log_summary_manager.get_memory_statistics()

            response = {
                "type": "memory_statistics",
                "timestamp": datetime.now().isoformat(),
                "statistics": stats,
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error sending memory statistics: {e}")

    def get_status_summary(self) -> Dict:
        """状態サマリーを取得"""
        memory_stats = self.log_summary_manager.get_memory_statistics()

        return {
            "agent_servers_count": len(self.agent_servers),
            "admin_clients_count": len(self.admin_clients),
            "active_sessions_count": len(self.active_sessions),
            "active_blocks_count": len(self.active_blocks),
            "total_block_history": len(self.block_history),
            "total_log_summaries": memory_stats.get("total_summaries", 0),
            "total_memories": memory_stats.get("total_memories", 0),
            "last_activity": datetime.now().isoformat(),
        }
