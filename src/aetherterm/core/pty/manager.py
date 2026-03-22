"""PTYManager — spawns and manages PTY session lifecycles.

Service-agnostic: does not know about tmux, tenants, or tool presets.
Callers provide cmd, env, and cwd; this module handles fork, read loop,
and graceful termination.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import signal
from typing import Callable, Coroutine, Dict, List, Optional

from .session import PTYSession

log = logging.getLogger("aetherterm.core.pty.manager")

# Default environment set on every child process
_DEFAULT_CHILD_ENV = {
    "TERM": "xterm-256color",
}


class PTYManager:
    """Manages multiple PTY sessions with async read loops.

    Unlike the old PTYSessionManager singleton, this is a plain class
    that can be instantiated per-service for better testability and
    isolation.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, PTYSession] = {}
        self._output_callbacks: List[Callable[[str, bytes], Coroutine]] = []

    # --- Callbacks ---

    def on_output(self, callback: Callable[[str, bytes], Coroutine]) -> None:
        """Register a callback invoked on PTY output.

        Signature: async (session_id: str, data: bytes) -> None
        """
        self._output_callbacks.append(callback)

    # --- CRUD ---

    async def spawn(
        self,
        session_id: str,
        cmd: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        cols: int = 80,
        rows: int = 24,
    ) -> PTYSession:
        """Fork a new PTY process and start its read loop.

        Args:
            session_id: Unique identifier for the session.
            cmd: Command to execute. Defaults to $SHELL or /bin/bash.
            env: Additional environment variables merged into the child env.
                 Overrides defaults (TERM=xterm-256color).
            cwd: Working directory for the child. None = inherit parent cwd.
            cols: Initial terminal width.
            rows: Initial terminal height.

        Returns:
            The created PTYSession.
        """
        if session_id in self._sessions:
            return self._sessions[session_id]

        if cmd is None:
            cmd = [os.environ.get("SHELL", "/bin/bash")]

        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:
            # ---- Child process ----
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.close(master_fd)

            if cwd:
                try:
                    os.chdir(cwd)
                except OSError:
                    pass

            child_env = os.environ.copy()
            child_env.update(_DEFAULT_CHILD_ENV)
            if env:
                child_env.update(env)

            try:
                os.execvpe(cmd[0], cmd, child_env)
            except Exception:
                os._exit(1)

        # ---- Parent process ----
        os.close(slave_fd)
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        session = PTYSession(
            session_id=session_id,
            master_fd=master_fd,
            pid=pid,
            cols=cols,
            rows=rows,
        )
        session.resize(cols, rows)
        self._sessions[session_id] = session

        # Start async read loop
        session._read_task = asyncio.create_task(
            self._read_loop(session),
            name=f"pty-read-{session_id}",
        )

        log.info("Spawned PTY %s (pid=%d, cmd=%s)", session_id, pid, cmd)
        return session

    def get(self, session_id: str) -> Optional[PTYSession]:
        """Get a session by ID, or None."""
        return self._sessions.get(session_id)

    def list_all(self) -> List[PTYSession]:
        """Return all active sessions."""
        return list(self._sessions.values())

    async def kill(self, session_id: str) -> None:
        """Terminate a session: cancel read loop, close fd, signal child.

        Uses SIGTERM first, then SIGKILL after 5s if still alive.
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            return

        # Cancel read task
        if session._read_task and not session._read_task.done():
            session._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session._read_task

        # Close fd
        session.close_fd()

        # Kill child
        if session.pid > 0:
            try:
                os.kill(session.pid, signal.SIGTERM)
                await asyncio.sleep(0.1)
                try:
                    os.waitpid(session.pid, os.WNOHANG)
                except ChildProcessError:
                    pass
                else:
                    try:
                        os.kill(session.pid, 0)  # Check if still alive
                        asyncio.get_event_loop().call_later(
                            5.0, _force_kill, session.pid
                        )
                    except OSError:
                        pass  # Already dead
            except OSError:
                pass

        # Signal all clients
        session.signal_clients_eof()
        log.info("Killed PTY %s", session_id)

    async def cleanup_all(self) -> None:
        """Destroy all sessions. Call on server shutdown."""
        for session_id in list(self._sessions.keys()):
            await self.kill(session_id)

    # --- Read loop ---

    async def _read_loop(self, session: PTYSession) -> None:
        """Async read loop: reads PTY output and broadcasts to clients."""
        while session.session_id in self._sessions:
            try:
                await asyncio.sleep(0.01)
                data = os.read(session.master_fd, 65536)
                if not data:
                    break

                session.append_history(data)
                session.broadcast(data)

                # Notify output callbacks
                for cb in self._output_callbacks:
                    try:
                        await cb(session.session_id, data)
                    except Exception:
                        log.exception("Output callback error")

            except BlockingIOError:
                await asyncio.sleep(0.01)
            except OSError:
                break
            except Exception:
                log.exception("Read loop error for %s", session.session_id)
                break

        # Process exited — remove from sessions and notify
        self._sessions.pop(session.session_id, None)
        session.signal_clients_eof()
        log.info("PTY %s read loop ended", session.session_id)


def _force_kill(pid: int) -> None:
    """SIGKILL fallback after timeout."""
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, os.WNOHANG)
