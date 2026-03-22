"""Session registry for tmux-style session/window/pane hierarchy.

Manages PTY lifecycle: fork, async read, resize, cleanup.
Follows PTYSessionManager patterns from session_manager.py.
"""

from __future__ import annotations

import array
import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import signal
import termios
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .layout_engine import LayoutEngine
from .models import (
    LayoutNode,
    LayoutType,
    PaneStatus,
    TmuxPane,
    TmuxSession,
    TmuxWindow,
)
from .preset_layouts import PRESET_LAYOUTS
from .wm_socket import default_socket_path

log = logging.getLogger("aetherterm.tmux.registry")


class TmuxSessionRegistry:
    """Manages tmux sessions, windows, panes, and their PTY processes."""

    _instance: Optional[TmuxSessionRegistry] = None
    _initialized: bool = False

    def __new__(cls) -> TmuxSessionRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self.sessions: Dict[str, TmuxSession] = {}
        self._state_callbacks: List[Callable[..., Coroutine]] = []
        self._output_callbacks: List[Callable[[str, str, bytes], Coroutine]] = []
        self.message_router: Optional[Any] = None  # Set externally by server.py

    def on_state_change(self, callback: Callable[..., Coroutine]) -> None:
        """Register a callback for state changes.

        Callback signature: async (session_id: str, event: dict) -> None
        """
        self._state_callbacks.append(callback)

    async def _notify_state_change(self, session_id: str, event: Dict[str, Any]) -> None:
        """Notify all registered callbacks of a state change."""
        for cb in self._state_callbacks:
            try:
                await cb(session_id, event)
            except Exception:
                log.exception("State change callback error")

    def on_pane_output(self, callback: Callable[[str, str, bytes], Coroutine]) -> None:
        """Register a callback for raw PTY output.

        Callback signature: async (session_id: str, pane_id: str, data: bytes) -> None
        """
        self._output_callbacks.append(callback)

    async def _notify_pane_output(self, session_id: str, pane_id: str, data: bytes) -> None:
        """Notify output callbacks (e.g. ControlBridge log forwarding)."""
        for cb in self._output_callbacks:
            try:
                await cb(session_id, pane_id, data)
            except Exception:
                log.exception("Pane output callback error")

    # --- Session CRUD ---

    def create_session(self, name: str = "", session_id: str = "") -> TmuxSession:
        """Create a new tmux session with one window and one pane."""
        session = TmuxSession(name=name or "main")
        if session_id:
            session.session_id = session_id
        self.sessions[session.session_id] = session
        log.info(f"Created session {session.session_id} ({session.name})")
        return session

    def get_session(self, session_id: str) -> Optional[TmuxSession]:
        return self.sessions.get(session_id)

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session and all its windows/panes."""
        session = self.sessions.pop(session_id, None)
        if session is None:
            return

        for window in list(session.windows.values()):
            for pane in list(window.panes.values()):
                await self._kill_pane(pane)

        # Signal all clients
        for q in session.client_queues:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)

        await self._notify_state_change(session_id, {"type": "session_destroy"})
        log.info(f"Destroyed session {session_id}")

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]

    # --- Window CRUD ---

    async def create_window(
        self,
        session_id: str,
        name: str = "",
        cmd: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        role: str = "",
    ) -> Optional[TmuxWindow]:
        """Create a new window in a session with an initial pane."""
        session = self.sessions.get(session_id)
        if session is None:
            return None

        window = TmuxWindow(
            window_index=session.next_window_index,
            name=name or f"window-{session.next_window_index}",
        )
        session.next_window_index += 1

        # Create initial pane
        pane = await self._fork_pane(cmd, env=env, role=role)
        window.panes[pane.pane_id] = pane
        window.active_pane_id = pane.pane_id
        window.layout = LayoutNode(type=LayoutType.LEAF, pane_id=pane.pane_id)

        session.windows[window.window_id] = window
        if not session.active_window_id:
            session.active_window_id = window.window_id

        # Start read loop AFTER pane is registered in window
        self._start_read_loop(pane, session_id)

        await self._notify_state_change(
            session_id,
            {
                "type": "window_create",
                "window": window.to_dict(),
            },
        )
        log.info(f"Created window {window.window_id} in session {session_id}")
        return window

    async def close_window(self, session_id: str, window_id: str) -> bool:
        """Close a window and all its panes."""
        session = self.sessions.get(session_id)
        if session is None:
            return False

        window = session.windows.pop(window_id, None)
        if window is None:
            return False

        for pane in list(window.panes.values()):
            await self._kill_pane(pane)

        # If active window was closed, switch to another
        if session.active_window_id == window_id:
            if session.windows:
                session.active_window_id = next(iter(session.windows))
            else:
                session.active_window_id = ""

        await self._notify_state_change(
            session_id,
            {
                "type": "window_close",
                "window_id": window_id,
            },
        )
        return True

    def select_window(self, session_id: str, window_id: str) -> bool:
        """Switch the active window."""
        session = self.sessions.get(session_id)
        if session is None or window_id not in session.windows:
            return False
        session.active_window_id = window_id
        return True

    # --- Pane CRUD ---

    async def split_pane(
        self,
        session_id: str,
        window_id: str,
        target_pane_id: str = "",
        direction: str = "v",
        cmd: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        role: str = "",
    ) -> Optional[TmuxPane]:
        """Split a pane in half, creating a new pane."""
        session = self.sessions.get(session_id)
        if session is None:
            return None

        window = session.windows.get(window_id)
        if window is None:
            return None

        if not target_pane_id:
            target_pane_id = window.active_pane_id

        if target_pane_id not in window.panes:
            return None

        new_pane = await self._fork_pane(cmd, env=env, role=role)
        window.panes[new_pane.pane_id] = new_pane

        # Start read loop AFTER pane is registered in window
        self._start_read_loop(new_pane, session_id)

        # Update layout
        window.layout = LayoutEngine.split(
            window.layout, target_pane_id, new_pane.pane_id, direction
        )

        await self._notify_state_change(
            session_id,
            {
                "type": "pane_split",
                "window_id": window_id,
                "pane": new_pane.to_dict(),
                "layout": window.layout.to_dict(),
            },
        )
        log.info(f"Split pane {target_pane_id} → {new_pane.pane_id} ({direction})")
        return new_pane

    async def close_pane(
        self,
        session_id: str,
        window_id: str,
        pane_id: str,
    ) -> bool:
        """Close a pane. If last pane in window, closes the window."""
        session = self.sessions.get(session_id)
        if session is None:
            return False

        window = session.windows.get(window_id)
        if window is None:
            return False

        pane = window.panes.pop(pane_id, None)
        if pane is None:
            return False

        await self._kill_pane(pane)

        if not window.panes:
            # Last pane — close window
            return await self.close_window(session_id, window_id)

        # Update layout
        new_layout = LayoutEngine.remove(window.layout, pane_id)
        window.layout = new_layout or LayoutNode(type=LayoutType.LEAF)

        # Update active pane if needed
        if window.active_pane_id == pane_id:
            window.active_pane_id = next(iter(window.panes))

        await self._notify_state_change(
            session_id,
            {
                "type": "pane_close",
                "window_id": window_id,
                "pane_id": pane_id,
                "layout": window.layout.to_dict(),
            },
        )
        return True

    def focus_pane(self, session_id: str, window_id: str, pane_id: str) -> bool:
        """Set the active pane."""
        session = self.sessions.get(session_id)
        if session is None:
            return False
        window = session.windows.get(window_id)
        if window is None or pane_id not in window.panes:
            return False
        window.active_pane_id = pane_id
        return True

    def resize_pane_pty(
        self,
        session_id: str,
        window_id: str,
        pane_id: str,
        cols: int,
        rows: int,
    ) -> bool:
        """Resize a pane's PTY."""
        pane = self._get_pane(session_id, window_id, pane_id)
        if pane is None:
            return False
        pane.cols = cols
        pane.rows = rows
        if pane.master_fd != -1:
            with contextlib.suppress(OSError):
                buf = array.array("h", [rows, cols, 0, 0])
                fcntl.ioctl(pane.master_fd, termios.TIOCSWINSZ, buf)
        return True

    def write_to_pane(self, session_id: str, window_id: str, pane_id: str, data: bytes) -> bool:
        """Write data to a pane's PTY."""
        pane = self._get_pane(session_id, window_id, pane_id)
        if pane is None or pane.master_fd == -1:
            return False
        if pane.status == PaneStatus.BLOCKED:
            return False
        with contextlib.suppress(OSError):
            os.write(pane.master_fd, data)
        return True

    def set_pane_blocked(
        self, session_id: str, window_id: str, pane_id: str, blocked: bool
    ) -> bool:
        """Block or unblock a pane's input."""
        pane = self._get_pane(session_id, window_id, pane_id)
        if pane is None:
            return False
        pane.status = PaneStatus.BLOCKED if blocked else PaneStatus.RUNNING
        return True

    # --- Layout Operations ---

    async def apply_preset_layout(
        self,
        session_id: str,
        window_id: str,
        preset: str,
    ) -> bool:
        """Apply a preset layout to a window."""
        session = self.sessions.get(session_id)
        if session is None:
            return False
        window = session.windows.get(window_id)
        if window is None:
            return False

        layout_fn = PRESET_LAYOUTS.get(preset)
        if layout_fn is None:
            return False

        pane_ids = list(window.panes.keys())
        window.layout = layout_fn(pane_ids)

        await self._notify_state_change(
            session_id,
            {
                "type": "layout_change",
                "window_id": window_id,
                "layout": window.layout.to_dict(),
            },
        )
        return True

    def resize_layout(
        self,
        session_id: str,
        window_id: str,
        pane_id: str,
        delta: float,
    ) -> bool:
        """Adjust the split ratio near a pane."""
        session = self.sessions.get(session_id)
        if session is None:
            return False
        window = session.windows.get(window_id)
        if window is None:
            return False
        window.layout = LayoutEngine.resize(window.layout, pane_id, delta)
        return True

    # --- PTY Lifecycle ---

    async def _fork_pane(
        self,
        cmd: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        role: str = "",
    ) -> TmuxPane:
        """Fork a new PTY process for a pane.

        Args:
            cmd: Command to execute. Defaults to user's shell.
            env: Custom environment variables merged into the child process env.
                 AGENT_ID, PANE_ID, AGENTSERVER_URL are auto-set for agent connectivity.
            role: Semantic role label (e.g. "architect", "coder").
        """
        if cmd is None:
            cmd = [os.environ.get("SHELL", "/bin/bash")]

        # Pre-generate pane_id so we can inject it into env
        pane = TmuxPane(role=role)
        pane_id = pane.pane_id

        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:
            # Child process
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.close(master_fd)

            child_env = os.environ.copy()
            child_env["TERM"] = "xterm-256color"
            # Expose WM socket as TMUX env so tmux-shim can discover it
            child_env["TMUX"] = f"{default_socket_path()},0,0"
            child_env["WM_SOCKET"] = default_socket_path()
            # Auto-set agent connectivity vars
            child_env["PANE_ID"] = pane_id
            child_env["AGENT_ID"] = pane_id
            child_env.setdefault("AGENTSERVER_URL", "ws://localhost:57575")
            if role:
                child_env["AGENT_ROLE"] = role
            # Merge caller-provided env (overrides defaults)
            if env:
                child_env.update(env)
            try:
                os.execvpe(cmd[0], cmd, child_env)
            except Exception:
                os._exit(1)

        # Parent
        os.close(slave_fd)
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        pane.master_fd = master_fd
        pane.child_pid = pid
        pane.env = env or {}
        # NOTE: read task is NOT started here. Callers must call
        # _start_read_loop() AFTER the pane is added to window.panes
        # so that session_id lookup succeeds.

        log.info(f"Forked pane {pane.pane_id} (pid={pid}, role={role!r})")
        return pane

    def _start_read_loop(self, pane: TmuxPane, session_id: str) -> None:
        """Start the async read loop for a pane with a known session_id."""
        pane._read_task = asyncio.create_task(self._read_loop(pane, session_id))

    async def _read_loop(self, pane: TmuxPane, session_id: str = "") -> None:
        """Async read loop for a pane's PTY output."""

        while pane.status != PaneStatus.EXITED:
            try:
                await asyncio.sleep(0.01)
                data = os.read(pane.master_fd, 65536)
                if not data:
                    break

                pane.history.extend(data)
                pane.trim_history()

                for q in list(pane.clients):
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(data)

                # Forward to output callbacks (ControlBridge log stream)
                if self._output_callbacks:
                    await self._notify_pane_output(session_id, pane.pane_id, data)

            except BlockingIOError:
                await asyncio.sleep(0.01)
            except OSError:
                break
            except Exception:
                log.exception(f"Read loop error for pane {pane.pane_id}")
                break

        # Process exited
        pane.status = PaneStatus.EXITED
        try:
            _, status = os.waitpid(pane.child_pid, os.WNOHANG)
            pane.exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            pane.exit_code = -1

        # Notify clients
        for q in list(pane.clients):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)

        log.info(f"Pane {pane.pane_id} exited (code={pane.exit_code})")

        # Notify state change for all sessions containing this pane
        for session in self.sessions.values():
            for window in session.windows.values():
                if pane.pane_id in window.panes:
                    await self._notify_state_change(
                        session.session_id,
                        {
                            "type": "pane_exited",
                            "window_id": window.window_id,
                            "pane_id": pane.pane_id,
                            "exit_code": pane.exit_code,
                        },
                    )

    async def _kill_pane(self, pane: TmuxPane) -> None:
        """Terminate a pane's PTY process."""
        if pane._read_task and not pane._read_task.done():
            pane._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pane._read_task

        if pane.master_fd != -1:
            with contextlib.suppress(OSError):
                os.close(pane.master_fd)
            pane.master_fd = -1

        if pane.child_pid > 0:
            try:
                os.kill(pane.child_pid, signal.SIGTERM)
                # Give it 5 seconds then SIGKILL
                await asyncio.sleep(0.1)
                try:
                    os.waitpid(pane.child_pid, os.WNOHANG)
                except ChildProcessError:
                    pass
                else:
                    try:
                        os.kill(pane.child_pid, 0)
                        # Still alive — schedule SIGKILL
                        asyncio.get_event_loop().call_later(5.0, self._force_kill, pane.child_pid)
                    except OSError:
                        pass  # Already dead
            except OSError:
                pass
            pane.child_pid = -1

        pane.status = PaneStatus.EXITED

        for q in list(pane.clients):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)

    @staticmethod
    def _force_kill(pid: int) -> None:
        """SIGKILL fallback after timeout."""
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, os.WNOHANG)

    # --- Helpers ---

    def _get_pane(
        self,
        session_id: str,
        window_id: str,
        pane_id: str,
    ) -> Optional[TmuxPane]:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        window = session.windows.get(window_id)
        if window is None:
            return None
        return window.panes.get(pane_id)

    def find_pane_location(
        self,
        pane_id: str,
    ) -> Optional[tuple[str, str]]:
        """Find which session/window a pane belongs to.

        Returns:
            (session_id, window_id) tuple or None.
        """
        for session in self.sessions.values():
            for window in session.windows.values():
                if pane_id in window.panes:
                    return (session.session_id, window.window_id)
        return None

    async def cleanup_all(self) -> None:
        """Destroy all sessions (for server shutdown)."""
        for session_id in list(self.sessions.keys()):
            await self.destroy_session(session_id)
