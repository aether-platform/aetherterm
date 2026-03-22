"""PTY session management — delegates to shared core.

Backward-compatible re-exports:
    from aetherterm.agentserver.core.sessions.manager import PTYSession, PTYSessionManager

The actual PTYSession implementation lives in aetherterm.core.pty.session.
PTYSessionManager is a thin singleton wrapper around core.pty.PTYManager.
"""

import asyncio
import contextlib
import fcntl
import logging
import os
import pty
from typing import Dict, List, Optional

from aetherterm.core.pty.manager import PTYManager
from aetherterm.core.pty.session import PTYSession

log = logging.getLogger("aetherterm.pty_manager")


class PTYSessionManager:
    """Singleton wrapper around the shared PTYManager.

    Preserves the old synchronous create_session/remove_session interface.
    For async code, use .manager directly.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._manager = PTYManager()
            cls._instance = inst
        return cls._instance

    @property
    def manager(self) -> PTYManager:
        """Access the underlying async PTYManager."""
        return self._manager

    @property
    def sessions(self) -> Dict[str, PTYSession]:
        return self._manager._sessions

    def create_session(self, session_id: str, cmd: Optional[List[str]] = None) -> PTYSession:
        """Create or get a PTY session (synchronous).

        This performs the fork synchronously (like the original implementation)
        and starts the async read loop as a background task. Safe to call from
        within a running event loop.
        """
        existing = self._manager.get(session_id)
        if existing is not None:
            return existing

        if cmd is None:
            cmd = [os.environ.get("SHELL", "bash")]

        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:  # Child
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.close(master_fd)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"

            try:
                os.execvpe(cmd[0], cmd, env)
            except Exception:
                os._exit(1)

        # Parent
        os.close(slave_fd)
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        session = PTYSession(session_id, master_fd, pid)
        self._manager._sessions[session_id] = session

        # Start the read loop from the shared manager
        session._read_task = asyncio.create_task(
            self._manager._read_loop(session),
            name=f"pty-read-{session_id}",
        )

        return session

    def remove_session(self, session_id: str) -> None:
        """Terminate and remove a PTY session (synchronous)."""
        session = self._manager._sessions.pop(session_id, None)
        if session is None:
            return
        session.close_fd()
        if session.pid > 0:
            with contextlib.suppress(OSError):
                os.kill(session.pid, os.SIGTERM)
        session.signal_clients_eof()
