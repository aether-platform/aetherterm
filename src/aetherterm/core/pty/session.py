"""PTYSession — represents a single PTY process.

Low-level wrapper around a forked child process with master fd.
Handles write, resize, history management, and client broadcast.
"""

from __future__ import annotations

import array
import asyncio
import contextlib
import fcntl
import logging
import os
import termios
from typing import Optional, Set

log = logging.getLogger("aetherterm.core.pty.session")

# History limits
MAX_HISTORY = 1024 * 1024   # 1 MB
TRIM_HISTORY = 1024 * 512   # 512 KB


class PTYSession:
    """Represents an individual PTY session process.

    Attributes:
        session_id: Unique identifier for this session.
        master_fd: File descriptor for the master side of the PTY pair.
        pid: OS process ID of the child.
        cols: Current terminal width.
        rows: Current terminal height.
        history: Circular output buffer (trimmed at MAX_HISTORY).
        clients: Set of asyncio.Queues that receive broadcast output.
    """

    def __init__(
        self,
        session_id: str,
        master_fd: int,
        pid: int,
        cols: int = 80,
        rows: int = 24,
    ) -> None:
        self.session_id = session_id
        # Keep .id as alias for backward compatibility with agentserver
        self.id = session_id
        self.master_fd = master_fd
        self.pid = pid
        self.cols = cols
        self.rows = rows
        self.history = bytearray()
        self.clients: Set[asyncio.Queue] = set()
        self._read_task: Optional[asyncio.Task] = None

    def write(self, data: bytes) -> None:
        """Write data to the PTY master fd."""
        if self.master_fd != -1:
            with contextlib.suppress(OSError):
                os.write(self.master_fd, data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal via TIOCSWINSZ ioctl."""
        self.cols = cols
        self.rows = rows
        if self.master_fd != -1:
            with contextlib.suppress(OSError):
                buf = array.array("h", [rows, cols, 0, 0])
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, buf)

    def broadcast(self, data: bytes) -> None:
        """Send data to all subscribed client queues."""
        for q in list(self.clients):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(data)

    def subscribe(self) -> asyncio.Queue:
        """Create and register a new output queue. Returns the queue."""
        q: asyncio.Queue = asyncio.Queue()
        self.clients.add(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a queue from the client set."""
        self.clients.discard(queue)

    def append_history(self, data: bytes) -> None:
        """Append data to history buffer, trimming if necessary."""
        self.history.extend(data)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-TRIM_HISTORY:]

    @property
    def is_alive(self) -> bool:
        """Check if the child process is still running."""
        if self.pid <= 0:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    def close_fd(self) -> None:
        """Close the master fd if open."""
        if self.master_fd != -1:
            with contextlib.suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = -1

    def signal_clients_eof(self) -> None:
        """Signal all client queues that the session has ended (put None)."""
        for q in list(self.clients):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)
