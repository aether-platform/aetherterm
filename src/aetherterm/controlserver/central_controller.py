"""CentralController - 中央制御システム

管理者からの制御指示を受信し、全AgentServerに一括指示を送信。
ログパターン圧縮 + LLM分析による異常検知・要約機能を統合。
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import websockets
from fastapi import FastAPI
from websockets.server import WebSocketServerProtocol

from aetherterm.common.models import BlockCommand, LogAnalysisResult, SessionInfo

from .blocking_manager import BlockingManager
from .health_monitor import HealthMonitor
from .llm_analyzer import LLMLogAnalyzer
from .log_analysis_config import LogAnalysisConfig
from .log_analysis_pipeline import LogAnalysisPipeline
from .log_buffer import LogBufferManager
from .log_pattern_compressor import LogPatternCompressor
from .metrics_collector import MetricsCollector
from .rest_api import create_rest_app as _create_rest_app
from .nats_controller import NATSController

logger = logging.getLogger(__name__)


class CentralController:
    """中央制御システム"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        log_analysis_config: LogAnalysisConfig | None = None,
    ):
        self.host = host
        self.port = port

        # 接続管理 — NATS agents + WebSocket admin clients
        self.agent_servers: Dict[str, WebSocketServerProtocol] = {}  # legacy WS agents
        self.nats_agents: Dict[str, str] = {}  # agent_id → status (NATS-registered)
        self.admin_clients: Set[WebSocketServerProtocol] = set()

        # NATS transport (created in start())
        self._nats_controller: Optional[NATSController] = None

        # 状態管理
        self.active_sessions: Dict[str, SessionInfo] = {}

        # Blocking manager (owns active_blocks + block_history)
        self._blocking_manager = BlockingManager(self)

        # AgentShell integration
        self._ai_cli_usage: Dict[str, Dict] = {}  # session_id -> {pane_id: info}

        # ログ分析パイプライン
        self._log_config = log_analysis_config or LogAnalysisConfig.from_env()
        self._log_compressor = LogPatternCompressor(self._log_config)
        self._llm_analyzer = LLMLogAnalyzer(self._log_config)

        # Log analysis pipeline (owns _analysis_history)
        self._log_pipeline = LogAnalysisPipeline(
            config=self._log_config,
            compressor=self._log_compressor,
            analyzer=self._llm_analyzer,
            controller=self,
        )

        self._log_buffer_manager = LogBufferManager(
            config=self._log_config,
            on_flush=self._log_pipeline.on_log_flush,
        )

        # Health monitor & Metrics collector
        self._health_monitor = HealthMonitor(self)
        self._metrics_collector = MetricsCollector(self)

        # WebSocketサーバー
        self.server = None

    # ------------------------------------------------------------------
    # Backward-compatible properties (state now in managers)
    # ------------------------------------------------------------------

    @property
    def active_blocks(self) -> Dict[str, BlockCommand]:
        return self._blocking_manager.active_blocks

    @property
    def block_history(self) -> List[BlockCommand]:
        return self._blocking_manager.block_history

    @property
    def _analysis_history(self) -> dict[str, list[LogAnalysisResult]]:
        return self._log_pipeline.analysis_history

    async def start(self):
        """中央制御サーバー開始"""
        logger.info(f"Starting CentralController on {self.host}:{self.port}")

        # Start NATS controller
        self._nats_controller = NATSController()
        self._nats_controller.on_log_received(self._handle_log_from_nats)
        self._nats_controller.on_session_report(self._handle_session_report_from_nats)
        await self._nats_controller.start()
        logger.info("NATS controller started")

        # Start WebSocket server for admin UI
        self.server = await websockets.serve(self.handle_connection, self.host, self.port)
        await self._log_buffer_manager.start_timer()

        # Start health monitor & metrics collector
        await self._health_monitor.start()
        await self._metrics_collector.start()

        logger.info(f"CentralController started on ws://{self.host}:{self.port}")

    async def stop(self):
        """中央制御サーバー停止"""
        await self._metrics_collector.stop()
        await self._health_monitor.stop()
        await self._log_buffer_manager.stop()

        # Stop NATS controller
        if self._nats_controller:
            await self._nats_controller.stop()

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
                    self._health_monitor.register_agent(agent_id, transport="websocket")
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
            elif message_type == "get_log_analysis":
                await self.handle_get_log_analysis(websocket, data)
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
        # Record activity as heartbeat
        if agent_id:
            self._health_monitor.record_heartbeat(agent_id)

        message_type = data.get("type")

        if message_type == "session_update":
            await self.update_session_info(data, agent_id)
        elif message_type == "block_confirmation":
            await self.handle_block_confirmation(data, agent_id)
        elif message_type == "unblock_request":
            await self.handle_unblock_request(data, agent_id)
        elif message_type == "ai_cli_detected":
            await self.handle_ai_cli_detected(data, agent_id)
        elif message_type == "log_aggregate":
            await self.handle_log_aggregate(data, agent_id)
        elif message_type == "input_block":
            await self.handle_pane_block(data, agent_id, block=True)
        elif message_type == "input_allow":
            await self.handle_pane_block(data, agent_id, block=False)
        elif message_type == "intervention_request":
            await self.handle_intervention_from_shell(data, agent_id)
        else:
            logger.debug(f"Received message from {agent_id}: {message_type}")

    async def execute_block_all(self, data: Dict):
        """全セッション一括ブロック実行"""
        await self._blocking_manager.execute_block_all(data)

    async def execute_block_session(self, data: Dict):
        """個別セッションブロック実行"""
        await self._blocking_manager.execute_block_session(data)

    async def execute_unblock_session(self, data: Dict):
        """セッションブロック解除実行"""
        await self._blocking_manager.execute_unblock_session(data)

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

    async def _handle_log_from_nats(self, agent_server_id: str, log_entries: list) -> None:
        """Handle log data received via NATS from AgentServer/AgentShell.

        log_entries may contain raw bytes (from PTY output) or structured dicts.
        Raw bytes are converted to structured entries for the analysis pipeline.
        """
        # Track NATS agents
        if agent_server_id and agent_server_id not in self.nats_agents:
            self.nats_agents[agent_server_id] = "active"
        if agent_server_id:
            self._health_monitor.record_heartbeat(agent_server_id)

        # Normalize entries: raw bytes → structured dicts for LogPatternCompressor
        structured_entries = []
        now_ts = time.time()
        for entry in log_entries:
            if isinstance(entry, (bytes, bytearray)):
                try:
                    text = entry.decode("utf-8", errors="replace")
                except Exception:
                    text = str(entry)
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        structured_entries.append({
                            "text": line,
                            "timestamp": now_ts,
                            "source": agent_server_id,
                        })
            elif isinstance(entry, dict):
                structured_entries.append(entry)
            elif isinstance(entry, str):
                if entry.strip():
                    structured_entries.append({
                        "text": entry.strip(),
                        "timestamp": now_ts,
                        "source": agent_server_id,
                    })

        if not structured_entries:
            return

        await self.handle_log_aggregate(
            {"session_id": agent_server_id, "entries": structured_entries},
            agent_server_id,
        )

    async def _handle_session_report_from_nats(self, agent_server_id: str, report: dict) -> None:
        """Handle session report received via NATS from AgentServer."""
        # Track NATS agents
        if agent_server_id and agent_server_id not in self.nats_agents:
            self.nats_agents[agent_server_id] = "active"
        if agent_server_id:
            self._health_monitor.record_heartbeat(agent_server_id)

        await self.update_session_info(report, agent_server_id)

    async def broadcast_to_agents(self, message: Dict):
        """全AgentServerに一括送信（NATS + WebSocket）"""
        sent_count = 0

        # NATS broadcast via NATSController
        if self._nats_controller:
            msg_type_str = message.get("type", "")
            try:
                if msg_type_str == "emergency_block":
                    await self._nats_controller.send_emergency_stop()
                    sent_count += len(self.nats_agents)
                elif msg_type_str == "unblock_session":
                    await self._nats_controller.send_unblock_input()
                    sent_count += len(self.nats_agents)
                elif msg_type_str == "input_block":
                    await self._nats_controller.send_block_input()
                    sent_count += len(self.nats_agents)
                elif msg_type_str == "input_allow":
                    await self._nats_controller.send_unblock_input()
                    sent_count += len(self.nats_agents)
            except Exception:
                logger.exception("Failed to broadcast via NATS controller")

        # Legacy WebSocket broadcast
        if self.agent_servers:
            message_json = json.dumps(message)
            tasks = []
            for agent_id, websocket in self.agent_servers.items():
                tasks.append(self.safe_send(websocket, message_json, agent_id))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent_count += sum(1 for r in results if r is True)

        if sent_count == 0 and not self.agent_servers and not self.nats_agents:
            logger.warning("No AgentServers connected for broadcast")
        else:
            logger.info(f"Broadcast sent to {sent_count} AgentServers")

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
            "sessions": [session.model_dump() for session in self.active_sessions.values()],
            "blocks": [block.model_dump() for block in self.active_blocks.values()],
        }

        await websocket.send(json.dumps(status))

    async def send_block_history(self, websocket: WebSocketServerProtocol):
        """ブロック履歴を送信"""
        history = {
            "type": "block_history",
            "timestamp": datetime.now().isoformat(),
            "total_blocks": len(self.block_history),
            "history": [block.model_dump() for block in self.block_history[-50:]],  # 最新50件
        }

        await websocket.send(json.dumps(history))

    async def handle_block_confirmation(self, data: Dict, agent_id: str):
        """ブロック確認処理"""
        await self._blocking_manager.handle_block_confirmation(data, agent_id)

    async def handle_unblock_request(self, data: Dict, agent_id: str):
        """ブロック解除要求処理"""
        await self._blocking_manager.handle_unblock_request(data, agent_id)

    # --- AgentShell integration handlers ---

    async def handle_ai_cli_detected(self, data: Dict, agent_id: str):
        """AI CLI検出の処理"""
        pane_id = data.get("pane_id", "")
        cli_name = data.get("cli_name", "unknown")
        session_id = data.get("session_id", "")

        # Track AI CLI usage
        if session_id not in self._ai_cli_usage:
            self._ai_cli_usage[session_id] = {}
        self._ai_cli_usage[session_id][pane_id] = {
            "cli_name": cli_name,
            "detected_at": datetime.now().isoformat(),
            "agent_id": agent_id,
        }

        logger.info(f"AI CLI detected: {cli_name} in pane {pane_id} (session={session_id})")

        # Notify admins
        await self.broadcast_to_admins(
            {
                "type": "ai_cli_detected",
                "session_id": session_id,
                "pane_id": pane_id,
                "cli_name": cli_name,
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_log_aggregate(self, data: Dict, agent_id: str):
        """ログ集約の処理 → バッファに委譲"""
        session_id = data.get("session_id", "")
        log_entries = data.get("entries", [])

        # リアルタイム生ログは引き続き管理者にブロードキャスト
        await self.broadcast_to_admins(
            {
                "type": "log_aggregate",
                "session_id": session_id,
                "entries": log_entries,
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # バッファに追加（閾値到達時に自動フラッシュ → 圧縮 → 分析）
        await self._log_buffer_manager.add(session_id, log_entries)

    async def handle_get_log_analysis(self, websocket, data: dict) -> None:
        """オンデマンドのログ分析結果取得"""
        await self._log_pipeline.handle_get_log_analysis(websocket, data)

    async def handle_pane_block(self, data: Dict, agent_id: str, block: bool):
        """ペインレベルのブロック/アンブロック"""
        pane_id = data.get("pane_id", "")
        session_id = data.get("session_id", "")
        reason = data.get("reason", "")

        action = "blocked" if block else "unblocked"
        logger.info(f"Pane {pane_id} {action} in session {session_id}: {reason}")

        # Forward to the appropriate AgentServer
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            target_agent = session_info.agent_server_id
            if target_agent in self.agent_servers:
                msg = {
                    "type": "input_block" if block else "input_allow",
                    "pane_id": pane_id,
                    "session_id": session_id,
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }
                await self.safe_send(
                    self.agent_servers[target_agent], json.dumps(msg), target_agent
                )

        await self.broadcast_to_admins(
            {
                "type": "pane_block_update",
                "pane_id": pane_id,
                "session_id": session_id,
                "blocked": block,
                "reason": reason,
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_intervention_from_shell(self, data: Dict, agent_id: str):
        """AgentShellからの介入リクエスト処理"""
        session_id = data.get("session_id", "")
        threat_level = data.get("threat_level", "unknown")
        message = data.get("message", "")

        logger.warning(
            f"Intervention request from {agent_id}: "
            f"session={session_id}, threat={threat_level}, msg={message}"
        )

        await self.broadcast_to_admins(
            {
                "type": "intervention_request",
                "session_id": session_id,
                "threat_level": threat_level,
                "message": message,
                "agent_id": agent_id,
                "payload": data,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_status_summary(self) -> Dict:
        """状態サマリーを取得"""
        nats_status = {
            "connected": self._nats_controller is not None,
            "transport": "nats",
        }
        nats_detail = {}
        if self._nats_controller:
            nats_detail = self._nats_controller.get_status()

        health_summary = {}
        if self._health_monitor:
            health_summary = {
                "total_agents": self._health_monitor.total_agents,
                "healthy": self._health_monitor.get_healthy_count(),
                "unhealthy": self._health_monitor.get_unhealthy_agents(),
            }

        return {
            "agent_servers_count": len(self.agent_servers) + len(self.nats_agents),
            "ws_agent_servers_count": len(self.agent_servers),
            "nats_agent_servers_count": len(self.nats_agents),
            "admin_clients_count": len(self.admin_clients),
            "active_sessions_count": len(self.active_sessions),
            "active_blocks_count": len(self.active_blocks),
            "total_block_history": len(self.block_history),
            "nats": {**nats_status, **nats_detail},
            "agent_health": health_summary,
            "last_activity": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------

    def create_rest_app(self) -> FastAPI:
        """Create a FastAPI app exposing REST admin endpoints.

        Delegates to the extracted rest_api module.
        """
        return _create_rest_app(self)
