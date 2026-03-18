"""SDK session manager — thin wrapper around PTYSessionManager for multi-tenant use."""

import asyncio
import logging
import os
import pty
import uuid
from dataclasses import dataclass, field
from typing import Optional

from aetherterm.agentserver.core.sessions.manager import PTYSession, PTYSessionManager

log = logging.getLogger("agiterm.sessions")


@dataclass
class SDKSession:
    """An SDK terminal session scoped to a tenant."""

    session_id: str
    tenant_id: str
    user_id: str
    pty_session: PTYSession
    created_at: float = field(default_factory=lambda: __import__("time").time())
    label: str = ""


class SDKSessionManager:
    """Manages PTY sessions with tenant isolation.

    Each session is owned by a tenant + user pair.
    Reuses the core PTYSession for actual PTY operations.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SDKSession] = {}  # session_id -> SDKSession
        self._pty_manager = PTYSessionManager()

    async def create_session(
        self,
        tenant_id: str,
        user_id: str,
        shell: str = "/bin/bash",
        cols: int = 80,
        rows: int = 24,
        label: str = "",
    ) -> SDKSession:
        """Create a new PTY session for a tenant user."""
        session_id = f"sdk-{uuid.uuid4().hex[:12]}"

        # Fork a PTY process using pty.fork() for correct terminal setup
        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # Child process — exec the shell
            os.execvp(shell, [shell])

        # Parent process
        pty_session = PTYSession(
            session_id=session_id,
            master_fd=master_fd,
            pid=child_pid,
        )
        pty_session.resize(cols, rows)

        sdk_session = SDKSession(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            pty_session=pty_session,
            label=label,
        )

        self._sessions[session_id] = sdk_session
        log.info(
            "Created SDK session %s for tenant=%s user=%s",
            session_id, tenant_id, user_id,
        )
        return sdk_session

    def get_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> Optional[SDKSession]:
        """Get a session, enforcing tenant isolation."""
        session = self._sessions.get(session_id)
        if session and session.tenant_id == tenant_id:
            return session
        return None

    def list_sessions(self, tenant_id: str) -> list[SDKSession]:
        """List all sessions for a tenant."""
        return [
            s for s in self._sessions.values()
            if s.tenant_id == tenant_id
        ]

    async def destroy_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> bool:
        """Destroy a session, enforcing tenant isolation."""
        session = self.get_session(session_id, tenant_id)
        if not session:
            return False

        # Kill the PTY process
        try:
            os.kill(session.pty_session.pid, 9)
        except OSError:
            pass

        try:
            os.close(session.pty_session.master_fd)
        except OSError:
            pass

        del self._sessions[session_id]
        log.info("Destroyed SDK session %s", session_id)
        return True

    async def read_output(
        self,
        session: SDKSession,
    ) -> asyncio.Queue[bytes]:
        """Create an output queue for a session (for WebSocket streaming)."""
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        session.pty_session.clients.add(queue)

        # Start reading from master_fd if not already reading
        loop = asyncio.get_event_loop()
        loop.add_reader(
            session.pty_session.master_fd,
            self._on_pty_output,
            session.pty_session,
        )

        return queue

    def _on_pty_output(self, pty_session: PTYSession) -> None:
        """Callback when PTY has output ready."""
        try:
            data = os.read(pty_session.master_fd, 65536)
            if data:
                pty_session.history.extend(data)
                for queue in pty_session.clients:
                    queue.put_nowait(data)
        except OSError:
            pass
