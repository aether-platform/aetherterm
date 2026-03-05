"""
ControlIntegration - NATS-based integration between AgentServer and ControlServer.

Publishes session/terminal events to NATS and subscribes to control commands.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Set

from ..common.nats import NatsClient, Subjects
from .terminals.asyncio_terminal import AsyncioTerminal

logger = logging.getLogger(__name__)


class ControlIntegration:
    """NATS-based ControlServer integration."""

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        agent_id: str = "agentserver_main",
        # Legacy parameter kept for config compatibility
        control_server_url: str = None,
    ):
        self.agent_id = agent_id
        self.nats_url = nats_url

        # NATS client
        self._nats = NatsClient(servers=nats_url, name=f"agentserver-{agent_id}")

        # State
        self.is_running = False
        self.blocked_sessions: Set[str] = set()
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Callbacks
        self.on_block_session: Optional[Callable] = None
        self.on_unblock_session: Optional[Callable] = None
        self.sio_instance = None

    def set_socketio_instance(self, sio):
        """Set Socket.IO instance for client notifications."""
        self.sio_instance = sio

    def set_block_handlers(self, block_handler: Callable, unblock_handler: Callable):
        """Set block/unblock handlers."""
        self.on_block_session = block_handler
        self.on_unblock_session = unblock_handler

    async def start(self):
        """Start NATS integration."""
        if self.is_running:
            logger.warning("ControlIntegration is already running")
            return

        self.is_running = True
        logger.info(f"Starting ControlIntegration via NATS: {self.nats_url}")

        await self._nats.connect()

        # Subscribe to control commands directed at this agent
        await self._nats.subscribe(
            Subjects.control_command(self.agent_id), self._handle_control_command
        )
        # Subscribe to broadcast commands
        await self._nats.subscribe(
            Subjects.control_broadcast(), self._handle_control_command
        )

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Publish registration event
        await self._publish_status("registered")
        logger.info(f"ControlIntegration started: agent_id={self.agent_id}")

    async def stop(self):
        """Stop NATS integration."""
        if not self.is_running:
            return

        self.is_running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        await self._publish_status("disconnecting")
        await self._nats.close()
        logger.info("ControlIntegration stopped")

    # --- Event publishing (AgentServer → ControlServer) ---

    async def publish_session_event(self, event: str, session_id: str, data: Dict = None):
        """Publish session lifecycle event (created, closed, updated)."""
        await self._nats.publish(
            Subjects.agent_session(self.agent_id, event),
            {
                "agent_id": self.agent_id,
                "session_id": session_id,
                "event": event,
                "data": data or {},
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def publish_terminal_event(
        self, event: str, session_id: str, content: str, metadata: Dict = None
    ):
        """Publish terminal event (input, output)."""
        await self._nats.publish(
            Subjects.agent_terminal(self.agent_id, event),
            {
                "agent_id": self.agent_id,
                "session_id": session_id,
                "event": event,
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def send_session_update(self, session_id: str, session_data: Dict):
        """Publish session update (backward-compatible method)."""
        await self.publish_session_event("updated", session_id, session_data)

    async def send_unblock_request(self, session_id: str, user_action: str = "ctrl_d"):
        """Publish unblock request from user."""
        await self._nats.publish(
            Subjects.agent_session(self.agent_id, "unblock_request"),
            {
                "agent_id": self.agent_id,
                "session_id": session_id,
                "user_action": user_action,
                "timestamp": datetime.now().isoformat(),
            },
        )

    # --- Control command handling (ControlServer → AgentServer) ---

    async def _handle_control_command(self, subject: str, data: Dict[str, Any]):
        """Handle incoming control commands from ControlServer."""
        command = data.get("command")

        if command == "emergency_block":
            await self._handle_emergency_block(data)
        elif command == "block_session":
            session_id = data.get("session_id")
            message = data.get("message", "Session blocked by administrator")
            if session_id:
                if await self._block_session(session_id, message):
                    self.blocked_sessions.add(session_id)
        elif command == "unblock_session":
            await self._handle_unblock_session(data)
        elif command == "request_status":
            await self._publish_status("active")
        else:
            logger.debug(f"Unknown control command: {command}")

    async def _handle_emergency_block(self, data: Dict):
        """Handle emergency block command."""
        block_id = data.get("block_id")
        message = data.get("message", "Emergency block")
        action = data.get("action", "block_all_sessions")
        affected_sessions = data.get("affected_sessions", [])

        logger.warning(f"Emergency block received: {block_id} - {message}")

        if action == "block_all_sessions":
            sessions_to_block = list(AsyncioTerminal.sessions.keys())
        elif action == "block_session":
            sessions_to_block = affected_sessions
        else:
            logger.warning(f"Unknown block action: {action}")
            return

        blocked_count = 0
        for session_id in sessions_to_block:
            if await self._block_session(session_id, message):
                self.blocked_sessions.add(session_id)
                blocked_count += 1

        logger.info(f"Blocked {blocked_count} sessions")

        # Publish confirmation
        await self._nats.publish(
            Subjects.agent_session(self.agent_id, "block_confirmed"),
            {
                "agent_id": self.agent_id,
                "block_id": block_id,
                "confirmed_sessions": list(self.blocked_sessions),
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def _handle_unblock_session(self, data: Dict):
        """Handle unblock command."""
        session_id = data.get("session_id")

        if session_id in self.blocked_sessions:
            if await self._unblock_session(session_id):
                self.blocked_sessions.remove(session_id)
                logger.info(f"Unblocked session {session_id}")
        else:
            logger.warning(f"Session {session_id} is not blocked")

    async def _block_session(self, session_id: str, message: str) -> bool:
        """Block a session and notify connected clients."""
        try:
            if session_id not in AsyncioTerminal.sessions:
                logger.warning(f"Session {session_id} not found for blocking")
                return False

            terminal = AsyncioTerminal.sessions[session_id]

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
        """Unblock a session and notify connected clients."""
        try:
            if session_id not in AsyncioTerminal.sessions:
                logger.warning(f"Session {session_id} not found for unblocking")
                return False

            terminal = AsyncioTerminal.sessions[session_id]

            if self.sio_instance and hasattr(terminal, "client_sids"):
                for client_sid in terminal.client_sids:
                    await self.sio_instance.emit(
                        "input_unblock",
                        {"message": "Block has been lifted", "session_id": session_id},
                        room=client_sid,
                    )

            logger.info(f"Unblocked session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error unblocking session {session_id}: {e}")
            return False

    # --- Heartbeat ---

    async def _heartbeat_loop(self):
        """Periodically publish agent status."""
        while self.is_running:
            try:
                await self._publish_status("active")
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    async def _publish_status(self, status: str):
        """Publish current agent status."""
        await self._nats.publish(
            Subjects.agent_status(self.agent_id),
            {
                "agent_id": self.agent_id,
                "status": status,
                "active_sessions": len(AsyncioTerminal.sessions),
                "blocked_sessions": list(self.blocked_sessions),
                "timestamp": datetime.now().isoformat(),
            },
        )

    # --- Status query ---

    def is_session_blocked(self, session_id: str) -> bool:
        return session_id in self.blocked_sessions

    def get_status(self) -> Dict:
        return {
            "is_running": self.is_running,
            "is_connected": self._nats.is_connected,
            "nats_url": self.nats_url,
            "agent_id": self.agent_id,
            "blocked_sessions_count": len(self.blocked_sessions),
            "blocked_sessions": list(self.blocked_sessions),
        }
