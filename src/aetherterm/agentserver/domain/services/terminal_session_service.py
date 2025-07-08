"""
Terminal Session Service - Domain Layer

Manages terminal session lifecycle and orchestrates terminal operations.
This is a domain service that encapsulates business logic.
"""

import asyncio
import logging
from typing import Dict, Optional, Set, Callable
from datetime import datetime

from aetherterm.agentserver.domain.entities.terminals.base import BaseTerminal
from aetherterm.agentserver.infrastructure.terminal.pty_manager import PTYManager
from aetherterm.agentserver.infrastructure.terminal.buffer_manager import BufferManager

log = logging.getLogger(__name__)


class TerminalSession:
    """Domain entity representing a terminal session."""

    def __init__(self, session_id: str, user_name: str, path: str):
        self.session_id = session_id
        self.user_name = user_name
        self.path = path
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.client_sids: Set[str] = set()
        self.closed = False
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.rows = 24
        self.cols = 80

        # Callbacks
        self.output_callback: Optional[Callable] = None
        self.close_callback: Optional[Callable] = None


class TerminalSessionService:
    """
    Domain service for managing terminal sessions.
    Orchestrates terminal operations without dealing with infrastructure details.
    """

    def __init__(self, pty_manager: PTYManager, buffer_manager: BufferManager):
        self._pty_manager = pty_manager
        self._buffer_manager = buffer_manager
        self._sessions: Dict[str, TerminalSession] = {}
        self._read_tasks: Dict[str, asyncio.Task] = {}

    async def create_session(
        self,
        session_id: str,
        user_name: str,
        path: str,
        rows: int = 24,
        cols: int = 80,
        shell_cmd: Optional[str] = None,
    ) -> TerminalSession:
        """
        Create a new terminal session.

        Args:
            session_id: Unique session identifier
            user_name: User name for the session
            path: Working directory
            rows: Terminal rows
            cols: Terminal columns
            shell_cmd: Optional shell command

        Returns:
            Created terminal session
        """
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        # Create session
        session = TerminalSession(session_id, user_name, path)
        session.rows = rows
        session.cols = cols

        # Create PTY
        master_fd, slave_fd = self._pty_manager.create_pty(rows, cols)
        session.master_fd = master_fd
        session.slave_fd = slave_fd

        # Make master non-blocking for async reading
        self._pty_manager.make_non_blocking(master_fd)

        # Spawn shell
        pid = self._pty_manager.spawn_shell(slave_fd, user_name, path, shell_cmd)
        session.pid = pid

        # Store session
        self._sessions[session_id] = session

        # Start reading output
        read_task = asyncio.create_task(self._read_output_loop(session))
        self._read_tasks[session_id] = read_task

        log.info(f"Created terminal session {session_id} with PID {pid}")
        return session

    async def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """Get a terminal session by ID."""
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close a terminal session."""
        session = self._sessions.get(session_id)
        if not session:
            return

        session.closed = True

        # Cancel read task
        if session_id in self._read_tasks:
            self._read_tasks[session_id].cancel()
            del self._read_tasks[session_id]

        # Clean up PTY
        if session.master_fd is not None:
            self._pty_manager.cleanup_pty(session.master_fd, session.slave_fd, session.pid)

        # Clear buffer
        self._buffer_manager.clear_buffer(session_id)

        # Remove session
        del self._sessions[session_id]

        # Call close callback
        if session.close_callback:
            await session.close_callback(session_id)

        log.info(f"Closed terminal session {session_id}")

    async def write_to_session(self, session_id: str, data: str) -> bool:
        """
        Write data to a terminal session.

        Args:
            session_id: Session identifier
            data: Data to write

        Returns:
            True if successful, False otherwise
        """
        session = self._sessions.get(session_id)
        if not session or session.closed or session.master_fd is None:
            return False

        try:
            os.write(session.master_fd, data.encode())
            session.last_activity = datetime.now()
            return True
        except Exception as e:
            log.error(f"Error writing to session {session_id}: {e}")
            return False

    async def resize_session(self, session_id: str, rows: int, cols: int) -> bool:
        """
        Resize a terminal session.

        Args:
            session_id: Session identifier
            rows: New number of rows
            cols: New number of columns

        Returns:
            True if successful, False otherwise
        """
        session = self._sessions.get(session_id)
        if not session or session.closed or session.master_fd is None:
            return False

        try:
            self._pty_manager.set_terminal_size(session.master_fd, rows, cols)
            session.rows = rows
            session.cols = cols
            session.last_activity = datetime.now()
            return True
        except Exception as e:
            log.error(f"Error resizing session {session_id}: {e}")
            return False

    def add_client(self, session_id: str, client_sid: str) -> bool:
        """Add a client to a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.client_sids.add(client_sid)
        session.last_activity = datetime.now()
        return True

    def remove_client(self, session_id: str, client_sid: str) -> bool:
        """Remove a client from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.client_sids.discard(client_sid)
        return True

    def set_output_callback(self, session_id: str, callback: Callable) -> None:
        """Set output callback for a session."""
        session = self._sessions.get(session_id)
        if session:
            session.output_callback = callback

    def set_close_callback(self, session_id: str, callback: Callable) -> None:
        """Set close callback for a session."""
        session = self._sessions.get(session_id)
        if session:
            session.close_callback = callback

    def get_buffer_content(self, session_id: str) -> Optional[str]:
        """Get buffer content for a session."""
        return self._buffer_manager.get_buffer(session_id)

    def get_all_sessions(self) -> Dict[str, TerminalSession]:
        """Get all active sessions."""
        return self._sessions.copy()

    async def _read_output_loop(self, session: TerminalSession) -> None:
        """Read output from terminal in a loop."""
        import os
        import errno

        while not session.closed and session.master_fd is not None:
            try:
                # Read from PTY
                output = os.read(session.master_fd, 4096)
                if output:
                    output_str = output.decode("utf-8", errors="replace")

                    # Store in buffer
                    self._buffer_manager.append_to_buffer(session.session_id, output_str)

                    # Call output callback
                    if session.output_callback:
                        await session.output_callback(session.session_id, output_str)

                    session.last_activity = datetime.now()
                else:
                    # EOF - terminal closed
                    break

            except OSError as e:
                if e.errno == errno.EAGAIN:
                    # No data available, wait a bit
                    await asyncio.sleep(0.01)
                else:
                    # Real error
                    log.error(f"Error reading from session {session.session_id}: {e}")
                    break
            except Exception as e:
                log.error(f"Unexpected error in read loop for {session.session_id}: {e}")
                break

        # Terminal closed, clean up
        if not session.closed:
            await self.close_session(session.session_id)
