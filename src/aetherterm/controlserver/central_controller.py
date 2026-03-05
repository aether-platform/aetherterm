"""
CentralController - NATS-based central control system.

Subscribes to AgentServer events via NATS, performs real-time analysis
(command logging, security threat detection), and sends control commands.

ドメインサービス (BlockManagementService) とドメインエンティティを使用して
ビジネスロジックをインフラ層から分離しています。
"""

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..common.nats import NatsClient, Subjects
from .analyzers.command_log_analyzer import CommandLogAnalyzer
from .analyzers.threat_detector import ThreatDetector
from .domain.entities import AgentInfo, SessionInfo
from .domain.services.block_management import BlockManagementService

logger = logging.getLogger(__name__)


class CentralController:
    """NATS-based central control system with real-time analysis."""

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        host: str = "localhost",
        port: int = 8765,
    ):
        self.nats_url = nats_url

        # NATS client
        self._nats = NatsClient(servers=nats_url, name="controlserver")

        # Analyzers
        self.command_analyzer = CommandLogAnalyzer()
        self.threat_detector = ThreatDetector()

        # Domain services
        self._block_service = BlockManagementService()

        # State
        self.agents: Dict[str, AgentInfo] = {}
        self.active_sessions: Dict[str, SessionInfo] = {}

        # Admin notification callbacks
        self._admin_callbacks: List[Callable] = []

    @property
    def active_blocks(self):
        """後方互換性のため BlockManagementService のブロックを公開"""
        return self._block_service.active_blocks

    @property
    def block_history(self):
        """後方互換性のため BlockManagementService の履歴を公開"""
        return self._block_service.block_history

    async def start(self):
        """Start the central controller."""
        logger.info(f"Starting CentralController via NATS: {self.nats_url}")

        await self._nats.connect()

        # Wire up threat detector with NATS
        self.threat_detector.set_nats_client(self._nats)

        # Subscribe to agent events
        await self._nats.subscribe(
            Subjects.all_agent_sessions(), self._handle_session_event
        )
        await self._nats.subscribe(
            Subjects.all_agent_terminal(), self._handle_terminal_event
        )
        await self._nats.subscribe(
            Subjects.all_agent_status(), self._handle_agent_status
        )

        logger.info("CentralController started - listening for agent events")

    async def stop(self):
        """Stop the central controller."""
        await self._nats.close()
        logger.info("CentralController stopped")

    def register_admin_callback(self, callback: Callable) -> None:
        """Register a callback for admin notifications."""
        self._admin_callbacks.append(callback)

    # --- Event handlers (NATS subscriptions) ---

    async def _handle_session_event(self, subject: str, data: Dict[str, Any]) -> None:
        """Handle session lifecycle events from agents."""
        event = data.get("event", "")
        session_id = data.get("session_id", "")
        agent_id = data.get("agent_id", "")

        if event == "created":
            self.active_sessions[session_id] = SessionInfo(
                session_id=session_id,
                agent_server_id=agent_id,
                user_info=data.get("data", {}).get("user_info", {}),
                created_at=data.get("timestamp", datetime.now().isoformat()),
                last_activity=data.get("timestamp", datetime.now().isoformat()),
            )
            logger.info(f"Session created: {session_id} on {agent_id}")

        elif event == "closed":
            self.active_sessions.pop(session_id, None)
            self.command_analyzer.remove_session(session_id)
            logger.info(f"Session closed: {session_id}")

        elif event == "updated":
            if session_id in self.active_sessions:
                self.active_sessions[session_id].last_activity = data.get(
                    "timestamp", datetime.now().isoformat()
                )

        elif event == "block_confirmed":
            block_id = data.get("block_id")
            confirmed = data.get("confirmed_sessions", [])
            logger.info(f"Block confirmed by {agent_id}: {block_id} ({len(confirmed)} sessions)")
            await self._notify_admins(
                "block_confirmation",
                {"block_id": block_id, "agent_id": agent_id, "confirmed_sessions": confirmed},
            )

        elif event == "unblock_request":
            user_action = data.get("user_action", "unknown")
            logger.info(f"Unblock request: session={session_id} action={user_action}")

            # Auto-approve Ctrl+D unblock
            if user_action == "ctrl_d":
                await self.execute_unblock_session(session_id, admin_user="system_auto_unblock")

            await self._notify_admins(
                "unblock_request",
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "user_action": user_action,
                },
            )

    async def _handle_terminal_event(self, subject: str, data: Dict[str, Any]) -> None:
        """Handle terminal I/O events - route to analyzers."""
        event = data.get("event", "")

        if event == "input":
            await self.command_analyzer.handle_terminal_input(subject, data)
            await self.threat_detector.analyze_input(subject, data)

        elif event == "output":
            await self.command_analyzer.handle_terminal_output(subject, data)

    async def _handle_agent_status(self, subject: str, data: Dict[str, Any]) -> None:
        """Handle agent heartbeat/status updates."""
        agent_id = data.get("agent_id", "")
        status = data.get("status", "unknown")

        self.agents[agent_id] = AgentInfo(
            agent_id=agent_id,
            status=status,
            active_sessions=data.get("active_sessions", 0),
            last_heartbeat=data.get("timestamp", datetime.now().isoformat()),
        )

        if status == "registered":
            logger.info(f"Agent registered: {agent_id}")
        elif status == "disconnecting":
            logger.info(f"Agent disconnecting: {agent_id}")

    # --- Control commands (ControlServer → AgentServer) ---

    async def execute_block_all(
        self, reason: str = "Emergency block", admin_user: Optional[str] = None
    ) -> str:
        """Block all sessions across all agents."""
        affected = list(self.active_sessions.keys())
        block_command = self._block_service.create_block(
            block_type="admin_initiated",
            reason=reason,
            affected_sessions=affected,
            admin_user=admin_user,
        )

        logger.warning(f"Executing block all sessions: {reason} (ID: {block_command.block_id})")

        await self._nats.publish(
            Subjects.control_broadcast(),
            {
                "command": "emergency_block",
                "block_id": block_command.block_id,
                "action": "block_all_sessions",
                "message": f"Emergency block: {reason}",
                "affected_sessions": block_command.affected_sessions,
                "timestamp": block_command.timestamp,
            },
        )

        await self._notify_admins("block_executed", {"block_command": block_command.to_dict()})
        return block_command.block_id

    async def execute_block_session(
        self,
        session_id: str,
        reason: str = "Session blocked by administrator",
        admin_user: Optional[str] = None,
    ) -> Optional[str]:
        """Block a specific session."""
        if session_id not in self.active_sessions:
            logger.warning(f"Session not found for blocking: {session_id}")
            return None

        session_info = self.active_sessions[session_id]
        agent_id = session_info.agent_server_id

        block_command = self._block_service.create_block(
            block_type="admin_initiated",
            reason=reason,
            affected_sessions=[session_id],
            admin_user=admin_user,
        )

        await self._nats.publish(
            Subjects.control_command(agent_id),
            {
                "command": "block_session",
                "block_id": block_command.block_id,
                "session_id": session_id,
                "message": f"Blocked by administrator: {reason}",
                "timestamp": block_command.timestamp,
            },
        )

        logger.info(f"Blocked session {session_id}: {reason}")
        return block_command.block_id

    async def execute_unblock_session(
        self, session_id: str, admin_user: Optional[str] = None
    ) -> bool:
        """Unblock a session."""
        block_id = self._block_service.remove_block_for_session(session_id)

        if not block_id:
            logger.warning(f"No active block found for session: {session_id}")
            return False

        if session_id in self.active_sessions:
            agent_id = self.active_sessions[session_id].agent_server_id
            await self._nats.publish(
                Subjects.control_command(agent_id),
                {
                    "command": "unblock_session",
                    "session_id": session_id,
                    "admin_user": admin_user,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        logger.info(f"Unblocked session {session_id} by {admin_user}")
        return True

    # --- Admin notifications ---

    async def _notify_admins(self, event_type: str, data: Dict[str, Any]) -> None:
        """Notify registered admin callbacks."""
        notification = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data,
        }
        for callback in self._admin_callbacks:
            try:
                await callback(notification)
            except Exception as e:
                logger.error(f"Admin callback error: {e}")

    # --- Status & reporting ---

    def get_status_summary(self) -> Dict:
        """Get system status summary."""
        return {
            "agent_servers_count": len(self.agents),
            "active_sessions_count": len(self.active_sessions),
            "active_blocks_count": len(self._block_service.active_blocks),
            "total_block_history": len(self._block_service.block_history),
            "command_log_stats": self.command_analyzer.get_statistics(),
            "threat_stats": self.threat_detector.get_statistics(),
            "last_activity": datetime.now().isoformat(),
        }

    def get_agents(self) -> List[Dict]:
        """Get connected agents info."""
        return [agent.to_dict() for agent in self.agents.values()]

    def get_sessions(self) -> List[Dict]:
        """Get active sessions info."""
        return [session.to_dict() for session in self.active_sessions.values()]

    def get_block_history(self, limit: int = 50) -> List[Dict]:
        """Get block history."""
        return [block.to_dict() for block in self._block_service.get_block_history(limit)]
