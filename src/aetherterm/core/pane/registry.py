"""PaneRegistry — manages pane lifecycle with PTYManager.

Service-agnostic CRUD for panes. Callers (agentserver's TmuxSessionRegistry,
agiterm's SDKSessionManager) use this to avoid duplicating PTY fork/kill logic.
"""

from __future__ import annotations

import logging
from typing import Callable, Coroutine, Dict, List, Optional

from ..pty.manager import PTYManager
from ..pty.session import PTYSession
from .models import PaneConfig, PaneInfo, PaneStatus

log = logging.getLogger("aetherterm.core.pane.registry")


class PaneRegistry:
    """Manages pane creation, destruction, and lookup.

    Each pane owns a PTYSession managed by the given PTYManager.
    """

    def __init__(self, pty_manager: PTYManager) -> None:
        self._pty = pty_manager
        self._panes: Dict[str, PaneInfo] = {}

        # Callbacks
        self.on_created: List[Callable[[PaneInfo], Coroutine]] = []
        self.on_destroyed: List[Callable[[str], Coroutine]] = []

    async def create(self, config: PaneConfig, pane_id: str = "") -> PaneInfo:
        """Create a pane: spawn a PTY and register it.

        Args:
            config: Pane configuration (cmd, env, cwd, cols, rows, role, title).
            pane_id: Optional explicit pane ID. Auto-generated if empty.

        Returns:
            The created PaneInfo.
        """
        pane = PaneInfo(config=config)
        if pane_id:
            pane.pane_id = pane_id

        # Use pane_id as the PTY session_id for 1:1 mapping
        pty_session = await self._pty.spawn(
            session_id=pane.pane_id,
            cmd=config.cmd,
            env=config.env,
            cwd=config.cwd,
            cols=config.cols,
            rows=config.rows,
        )
        pane.pty_session_id = pty_session.session_id

        self._panes[pane.pane_id] = pane

        for cb in self.on_created:
            try:
                await cb(pane)
            except Exception:
                log.exception("on_created callback error")

        log.info("Created pane %s (role=%s)", pane.pane_id, config.role)
        return pane

    async def destroy(self, pane_id: str) -> bool:
        """Destroy a pane and kill its PTY.

        Returns True if found and destroyed.
        """
        pane = self._panes.pop(pane_id, None)
        if pane is None:
            return False

        await self._pty.kill(pane.pty_session_id)
        pane.status = PaneStatus.EXITED

        for cb in self.on_destroyed:
            try:
                await cb(pane_id)
            except Exception:
                log.exception("on_destroyed callback error")

        log.info("Destroyed pane %s", pane_id)
        return True

    def get(self, pane_id: str) -> Optional[PaneInfo]:
        """Get pane info by ID."""
        return self._panes.get(pane_id)

    def get_pty(self, pane_id: str) -> Optional[PTYSession]:
        """Get the PTYSession for a pane."""
        pane = self._panes.get(pane_id)
        if pane is None:
            return None
        return self._pty.get(pane.pty_session_id)

    def list_all(self) -> List[PaneInfo]:
        """Return all registered panes."""
        return list(self._panes.values())

    def set_status(self, pane_id: str, status: PaneStatus) -> bool:
        """Update a pane's status."""
        pane = self._panes.get(pane_id)
        if pane is None:
            return False
        pane.status = status
        return True

    async def cleanup_all(self) -> None:
        """Destroy all panes."""
        for pane_id in list(self._panes.keys()):
            await self.destroy(pane_id)
