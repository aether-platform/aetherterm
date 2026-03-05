"""BlockingManager — session blocking logic extracted from CentralController.

Owns ``active_blocks`` and ``block_history`` state.  Delegates broadcast
and per-agent messaging back to the parent controller.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from aetherterm.common.models import BlockCommand

if TYPE_CHECKING:
    from .central_controller import CentralController

logger = logging.getLogger(__name__)


class BlockingManager:
    """Manages session blocking / unblocking operations."""

    def __init__(self, controller: CentralController) -> None:
        self._ctrl = controller
        self.active_blocks: Dict[str, BlockCommand] = {}
        self.block_history: List[BlockCommand] = []

    # ------------------------------------------------------------------
    # Block all sessions
    # ------------------------------------------------------------------

    async def execute_block_all(self, data: Dict) -> None:
        block_id = str(uuid.uuid4())
        reason = data.get("reason", "管理者による緊急ブロック")
        admin_user = data.get("admin_user")

        block_command = BlockCommand(
            block_id=block_id,
            block_type="admin_initiated",
            reason=reason,
            admin_user=admin_user,
            affected_sessions=list(self._ctrl.active_sessions.keys()),
            timestamp=datetime.now().isoformat(),
        )

        self.active_blocks[block_id] = block_command
        self.block_history.append(block_command)

        logger.warning(f"Executing block all sessions: {reason} (ID: {block_id})")

        block_message = {
            "type": "emergency_block",
            "block_id": block_id,
            "severity": "admin_initiated",
            "message": f"管理者による緊急ブロック: {reason}",
            "action": "block_all_sessions",
            "affected_sessions": block_command.affected_sessions,
            "timestamp": block_command.timestamp,
        }

        await self._ctrl.broadcast_to_agents(block_message)
        await self._ctrl.broadcast_to_admins(
            {"type": "block_executed", "block_command": block_command.model_dump()}
        )

    # ------------------------------------------------------------------
    # Block individual session
    # ------------------------------------------------------------------

    async def execute_block_session(self, data: Dict) -> None:
        session_id = data.get("session_id")
        reason = data.get("reason", "管理者による個別ブロック")
        admin_user = data.get("admin_user")

        if session_id not in self._ctrl.active_sessions:
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

        session_info = self._ctrl.active_sessions[session_id]
        agent_id = session_info.agent_server_id

        if agent_id in self._ctrl.agent_servers:
            block_message = {
                "type": "emergency_block",
                "block_id": block_id,
                "severity": "admin_initiated",
                "message": f"管理者による個別ブロック: {reason}",
                "action": "block_session",
                "affected_sessions": [session_id],
                "timestamp": block_command.timestamp,
            }
            await self._ctrl.agent_servers[agent_id].send(json.dumps(block_message))

        logger.info(f"Executed block session {session_id}: {reason}")

    # ------------------------------------------------------------------
    # Unblock session
    # ------------------------------------------------------------------

    async def execute_unblock_session(self, data: Dict) -> None:
        session_id = data.get("session_id")
        admin_user = data.get("admin_user")

        block_to_remove: Optional[str] = None
        for block_id, block_cmd in self.active_blocks.items():
            if session_id in block_cmd.affected_sessions:
                block_to_remove = block_id
                break

        if not block_to_remove:
            logger.warning(f"No active block found for session: {session_id}")
            return

        del self.active_blocks[block_to_remove]

        if session_id in self._ctrl.active_sessions:
            session_info = self._ctrl.active_sessions[session_id]
            agent_id = session_info.agent_server_id

            if agent_id in self._ctrl.agent_servers:
                unblock_message = {
                    "type": "unblock_session",
                    "session_id": session_id,
                    "admin_user": admin_user,
                    "timestamp": datetime.now().isoformat(),
                }
                await self._ctrl.agent_servers[agent_id].send(json.dumps(unblock_message))

        logger.info(f"Executed unblock session {session_id} by {admin_user}")

    # ------------------------------------------------------------------
    # Confirmation & request handlers
    # ------------------------------------------------------------------

    async def handle_block_confirmation(self, data: Dict, agent_id: str) -> None:
        block_id = data.get("block_id")
        confirmed_sessions = data.get("confirmed_sessions", [])

        logger.info(
            f"Block confirmation from {agent_id}: {block_id}, "
            f"sessions: {len(confirmed_sessions)}"
        )

        await self._ctrl.broadcast_to_admins(
            {
                "type": "block_confirmation",
                "block_id": block_id,
                "agent_id": agent_id,
                "confirmed_sessions": confirmed_sessions,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_unblock_request(self, data: Dict, agent_id: str) -> None:
        session_id = data.get("session_id")
        user_action = data.get("user_action", "unknown")

        logger.info(
            f"Unblock request from {agent_id}: session {session_id}, action: {user_action}"
        )

        if user_action == "ctrl_d":
            await self.execute_unblock_session(
                {"session_id": session_id, "admin_user": "system_auto_unblock"}
            )

        await self._ctrl.broadcast_to_admins(
            {
                "type": "unblock_request",
                "session_id": session_id,
                "agent_id": agent_id,
                "user_action": user_action,
                "timestamp": datetime.now().isoformat(),
            }
        )
