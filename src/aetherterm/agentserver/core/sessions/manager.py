import array
import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import signal
import termios
from typing import Dict, List, Optional, Set

log = logging.getLogger("aetherterm.pty_manager")


class PTYSession:
    """Represents an individual PTY session process."""

    def __init__(self, session_id: str, master_fd: int, pid: int):
        """Initialize a PTY session."""
        self.id = session_id
        self.master_fd = master_fd
        self.pid = pid
        self.history = bytearray()
        self.clients: Set[asyncio.Queue] = set()

    def write(self, data: bytes) -> None:
        """Write data to the PTY."""
        if self.master_fd != -1:
            with contextlib.suppress(OSError):
                os.write(self.master_fd, data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal."""
        if self.master_fd != -1:
            with contextlib.suppress(OSError):
                buf = array.array("h", [rows, cols, 0, 0])
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, buf)


class PTYSessionManager:
    """Manages multiple PTY sessions."""

    _instance = None
    sessions: Dict[str, PTYSession] = {}

    def __new__(cls):
        """Singleton pattern for PTYSessionManager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def create_session(self, session_id: str, cmd: Optional[List[str]] = None) -> PTYSession:
        """Create or get a PTY session."""
        if session_id in self.sessions:
            return self.sessions[session_id]

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
        self.sessions[session_id] = session

        asyncio.create_task(self._read_loop(session))

        return session

    async def _read_loop(self, session: PTYSession) -> None:
        """Read output from the PTY."""
        while session.id in self.sessions:
            try:
                await asyncio.sleep(0.01)  # Yield
                data = os.read(session.master_fd, 65536)
                if not data:
                    break

                session.history.extend(data)
                if len(session.history) > 1024 * 1024:
                    session.history = session.history[-(1024 * 512) :]

                for q in list(session.clients):
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(data)
            except (BlockingIOError, OSError):
                await asyncio.sleep(0.01)
            except Exception:
                break

        self.remove_session(session.id)

    def remove_session(self, session_id: str) -> None:
        """Terminate and remove a PTY session."""
        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            with contextlib.suppress(OSError):
                os.close(session.master_fd)
                os.kill(session.pid, signal.SIGTERM)
            for q in session.clients:
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(None)
