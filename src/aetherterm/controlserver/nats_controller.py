"""NATSController -- ControlServer NATS transport layer.

Subscribes to AgentServer/AgentShell messages
via NATS and provides methods to send commands back.

Subscriptions (ControlServer receives):
    aether.terminal.agentserver.*.register
    aether.terminal.agentserver.*.heartbeat
    aether.terminal.agentserver.*.report.session
    aether.terminal.agentserver.*.forward.log.>
    aether.terminal.agentshell.*.register
    aether.terminal.agentshell.*.heartbeat
    aether.terminal.agentshell.*.forward.log

Publishes (ControlServer sends):
    aether.terminal.controlserver.command.{agent_id}
    aether.terminal.controlserver.broadcast
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aetherterm.common.models import PaneDetail, PtySessionInfo, ShellInfo, WindowDetail
from aetherterm.common.nats_transport import (
    NATS_AVAILABLE,
    Subjects,
    connect_nats,
    make_envelope,
    pack_message,
    unpack_message,
)

log = logging.getLogger("aetherterm.nats_controller")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
LogCallback = Callable[[str, list], Awaitable[None]]
SessionReportCallback = Callable[[str, dict], Awaitable[None]]
EventCallback = Callable[[str, str, dict], Awaitable[None]]


class NATSController:
    """ControlServer NATS transport with session mapping.

    Subscribes to AgentServer/AgentShell messages and maintains
    session/shell mapping for routing commands.
    """

    def __init__(self, nats_url: str = "") -> None:
        self._nats_url = nats_url
        self._nc: Any = None
        self._subscriptions: list = []

        # Registered AgentServers: agent_server_id -> last_heartbeat
        self._agents: Dict[str, float] = {}

        # Session mapping
        self._sessions: Dict[str, PtySessionInfo] = {}
        self._shells: Dict[str, ShellInfo] = {}
        self._agent_sessions: Dict[str, set[str]] = {}

        # Callbacks
        self._log_cb: Optional[LogCallback] = None
        self._session_report_cb: Optional[SessionReportCallback] = None
        self._event_cb: Optional[EventCallback] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_log_received(self, cb: LogCallback) -> None:
        self._log_cb = cb

    def on_session_report(self, cb: SessionReportCallback) -> None:
        self._session_report_cb = cb

    def on_event(self, cb: EventCallback) -> None:
        self._event_cb = cb

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        if not NATS_AVAILABLE:
            log.warning("nats-py not available -- NATSController will not start")
            return False

        try:
            self._nc = await connect_nats(
                name="controlserver",
                nats_url=self._nats_url or None,
            )

            # Subscribe to AgentServer messages
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentserver_register(),
                    cb=self._on_agentserver_register,
                )
            )
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentserver_heartbeat(),
                    cb=self._on_agentserver_heartbeat,
                )
            )
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentserver_report_session(),
                    cb=self._on_session_report,
                )
            )
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentserver_forward_log(),
                    cb=self._on_log_forward,
                )
            )

            # Subscribe to AgentShell messages
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentshell_register(),
                    cb=self._on_shell_register,
                )
            )
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentshell_heartbeat(),
                    cb=self._on_shell_heartbeat,
                )
            )
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.all_agentshell_forward_log(),
                    cb=self._on_shell_log,
                )
            )

            log.info("NATSController started")
            return True

        except Exception:
            log.exception("Failed to start NATSController")
            return False

    async def stop(self) -> None:
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        self._subscriptions.clear()

        if self._nc and self._nc.is_connected:
            await self._nc.drain()
            self._nc = None

        log.info("NATSController stopped")

    @property
    def is_connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    # ------------------------------------------------------------------
    # Outbound: ControlServer -> AgentServers
    # ------------------------------------------------------------------

    async def send_to_agent(
        self, agent_server_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a targeted command to a specific AgentServer."""
        if not self.is_connected:
            return False

        envelope = make_envelope(msg_type, "controlserver", payload)
        try:
            subject = Subjects.controlserver_command(agent_server_id)
            await self._nc.publish(subject, pack_message(envelope))
            return True
        except Exception as exc:
            log.warning("Failed to send to %s: %s", agent_server_id, exc)
            return False

    async def broadcast(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all AgentServers."""
        if not self.is_connected:
            return

        envelope = make_envelope(msg_type, "controlserver", payload)
        try:
            await self._nc.publish(
                Subjects.controlserver_broadcast(), pack_message(envelope)
            )
        except Exception as exc:
            log.warning("Broadcast error: %s", exc)

    async def send_emergency_stop(self, reason: str = "") -> None:
        await self.broadcast("emergency_stop", {"reason": reason})

    async def send_block_input(
        self, session_id: str = "", pane_id: str = "", reason: str = ""
    ) -> None:
        await self.broadcast(
            "block_input",
            {"session_id": session_id, "pane_id": pane_id, "reason": reason},
        )

    async def send_unblock_input(
        self, session_id: str = "", pane_id: str = "", admin_user: str = ""
    ) -> None:
        await self.broadcast(
            "unblock_input",
            {"session_id": session_id, "pane_id": pane_id, "admin_user": admin_user},
        )

    async def send_to_session(
        self, session_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a command to the AgentServer that owns a specific PTY session."""
        info = self._sessions.get(session_id)
        if not info:
            log.warning("Session %s not found in mapping", session_id)
            return False
        return await self.send_to_agent(info.agent_server_id, msg_type, payload)

    async def send_to_shell(
        self, shell_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a command targeting a specific AgentShell."""
        shell = self._shells.get(shell_id)
        if not shell:
            log.warning("Shell %s not found in mapping", shell_id)
            return False
        payload["target_shell_id"] = shell_id
        return await self.send_to_agent(shell.agent_server_id, msg_type, payload)

    # ------------------------------------------------------------------
    # Session mapping queries
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> Optional[PtySessionInfo]:
        return self._sessions.get(session_id)

    def get_shell(self, shell_id: str) -> Optional[ShellInfo]:
        return self._shells.get(shell_id)

    def list_sessions(self) -> List[PtySessionInfo]:
        return list(self._sessions.values())

    def list_shells(self) -> List[ShellInfo]:
        return list(self._shells.values())

    def get_sessions_for_agent(self, agent_server_id: str) -> List[PtySessionInfo]:
        session_ids = self._agent_sessions.get(agent_server_id, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_shells_for_session(self, session_id: str) -> List[ShellInfo]:
        info = self._sessions.get(session_id)
        if not info:
            return []
        return [self._shells[sid] for sid in info.shell_ids if sid in self._shells]

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "transport": "nats",
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "shells": len(self._shells),
        }

    # ------------------------------------------------------------------
    # Inbound message handlers
    # ------------------------------------------------------------------

    def _extract_agent_id(self, subject: str) -> str:
        """Extract agent_id from subject like aether.terminal.agentserver.{agent_id}.verb."""
        parts = subject.split(".")
        if len(parts) >= 4:
            return parts[3]
        return ""

    def _extract_session_id(self, subject: str) -> str:
        """Extract session_id from subject like aether.terminal.agentshell.{session_id}.verb."""
        parts = subject.split(".")
        if len(parts) >= 4:
            return parts[3]
        return ""

    async def _on_agentserver_register(self, msg) -> None:
        data = unpack_message(msg.data)
        agent_id = data.get("payload", {}).get("hostname", "") or data.get("sender_id", "")
        if not agent_id:
            agent_id = self._extract_agent_id(msg.subject)
        sender = data.get("sender_id", agent_id)
        self._agents[sender] = time.time()
        log.info("Agent registered via NATS: %s", sender)

        # Send ACK via command channel
        await self.send_to_agent(sender, "registration_confirmed", {
            "agent_server_id": sender,
        })

    async def _on_agentserver_heartbeat(self, msg) -> None:
        data = unpack_message(msg.data)
        agent_id = data.get("sender_id", self._extract_agent_id(msg.subject))
        self._agents[agent_id] = time.time()

    async def _on_session_report(self, msg) -> None:
        data = unpack_message(msg.data)
        agent_id = data.get("sender_id", self._extract_agent_id(msg.subject))
        payload = data.get("payload", {})

        self._update_session_mapping(agent_id, payload)

        if self._session_report_cb:
            try:
                await self._session_report_cb(agent_id, payload)
            except Exception:
                log.exception("session_report callback error")

    async def _on_log_forward(self, msg) -> None:
        data = unpack_message(msg.data)
        agent_id = data.get("sender_id", self._extract_agent_id(msg.subject))
        payload = data.get("payload", {})
        log_data = payload.get("data", "")
        session_id = payload.get("session_id", "")

        if self._log_cb and log_data:
            try:
                if isinstance(log_data, str):
                    log_data = log_data.encode("utf-8")
                await self._log_cb(agent_id, [log_data])
            except Exception:
                log.exception("log_received callback error")

        if session_id in self._sessions:
            self._sessions[session_id].last_activity = time.time()

    async def _on_shell_register(self, msg) -> None:
        data = unpack_message(msg.data)
        payload = data.get("payload", {})
        agent_id = data.get("sender_id", "")
        self._register_shell(agent_id, payload)

    async def _on_shell_heartbeat(self, msg) -> None:
        session_id = self._extract_session_id(msg.subject)
        if session_id in self._sessions:
            self._sessions[session_id].last_activity = time.time()

    async def _on_shell_log(self, msg) -> None:
        data = unpack_message(msg.data)
        session_id = self._extract_session_id(msg.subject)
        payload = data.get("payload", {})
        log_data = payload.get("data", "")

        if session_id in self._sessions:
            self._sessions[session_id].last_activity = time.time()

        if self._log_cb and log_data:
            try:
                if isinstance(log_data, str):
                    log_data = log_data.encode("utf-8")
                await self._log_cb(f"shell:{session_id}", [log_data])
            except Exception:
                log.exception("log_received callback error (shell)")

    # ------------------------------------------------------------------
    # Session mapping updates
    # ------------------------------------------------------------------

    def _update_session_mapping(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """Update internal session mapping from an AgentServer report."""
        sessions = payload.get("sessions", [])
        if not sessions and "session_id" in payload:
            sessions = [payload]

        reported_ids: set[str] = set()
        for s in sessions:
            sid = s.get("session_id", "")
            if not sid:
                continue
            reported_ids.add(sid)

            windows = _parse_windows(s.get("windows", []))

            if sid in self._sessions:
                info = self._sessions[sid]
                info.last_activity = time.time()
                info.pane_ids = s.get("pane_ids", info.pane_ids)
                info.name = s.get("name", info.name)
                info.user_info = s.get("user_info", info.user_info)
                if windows:
                    info.windows = windows
            else:
                info = PtySessionInfo(
                    session_id=sid,
                    agent_server_id=agent_id,
                    name=s.get("name", ""),
                    user_info=s.get("user_info", {}),
                    pane_ids=s.get("pane_ids", []),
                    windows=windows,
                    created_at=s.get("created_at", time.time()),
                )
                self._sessions[sid] = info
                log.info("New session mapped: %s on %s", sid, agent_id)

            self._agent_sessions.setdefault(agent_id, set()).add(sid)

            for shell_id in s.get("shell_ids", []):
                if shell_id not in self._shells:
                    self._shells[shell_id] = ShellInfo(
                        shell_id=shell_id,
                        session_id=sid,
                        agent_server_id=agent_id,
                    )
                    if shell_id not in info.shell_ids:
                        info.shell_ids.append(shell_id)

        # Prune sessions no longer reported
        existing = self._agent_sessions.get(agent_id, set())
        stale = existing - reported_ids
        for sid in stale:
            if sid in self._sessions:
                for shell_id in self._sessions[sid].shell_ids:
                    self._shells.pop(shell_id, None)
                del self._sessions[sid]
                log.info("Session removed from mapping: %s", sid)
        if stale:
            self._agent_sessions[agent_id] = existing - stale

    def _register_shell(self, agent_id: str, payload: Dict[str, Any]) -> None:
        shell_id = payload.get("shell_id", "")
        session_id = payload.get("session_id", "")
        if not shell_id or not session_id:
            return

        self._shells[shell_id] = ShellInfo(
            shell_id=shell_id,
            session_id=session_id,
            agent_server_id=agent_id,
        )

        if session_id in self._sessions:
            if shell_id not in self._sessions[session_id].shell_ids:
                self._sessions[session_id].shell_ids.append(shell_id)

        log.info("Shell registered: %s -> session %s", shell_id, session_id)

    def _unregister_shell(self, shell_id: str) -> None:
        shell = self._shells.pop(shell_id, None)
        if shell and shell.session_id in self._sessions:
            session = self._sessions[shell.session_id]
            if shell_id in session.shell_ids:
                session.shell_ids.remove(shell_id)
        if shell:
            log.info("Shell unregistered: %s", shell_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_windows(raw_windows: list) -> List[WindowDetail]:
    """Parse raw window dicts from session report into WindowDetail models."""
    result: List[WindowDetail] = []
    for w in raw_windows:
        panes = [
            PaneDetail(
                pane_id=p.get("pane_id", ""),
                status=p.get("status", "running"),
                role=p.get("role", ""),
                title=p.get("title", ""),
                cols=p.get("cols", 80),
                rows=p.get("rows", 24),
                exit_code=p.get("exit_code"),
                created_at=p.get("created_at", 0.0),
            )
            for p in w.get("panes", [])
        ]
        result.append(
            WindowDetail(
                window_id=w.get("window_id", ""),
                name=w.get("name", ""),
                active_pane_id=w.get("active_pane_id", ""),
                panes=panes,
            )
        )
    return result
