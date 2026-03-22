"""Data models for tmux-style session/window/pane hierarchy.

PaneStatus, LayoutType, and LayoutNode are re-exported from the shared core.
TmuxPane, TmuxWindow, TmuxSession are tmux-specific.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set
from uuid import uuid4

# Re-export shared models for backward compatibility
from aetherterm.core.pane.models import (
    LayoutNode,
    LayoutType,
    PaneStatus,
)


@dataclass
class TmuxPane:
    """A single terminal pane with its own PTY process."""

    pane_id: str = field(default_factory=lambda: f"pane_{uuid4().hex[:8]}")
    master_fd: int = -1
    child_pid: int = -1
    status: PaneStatus = PaneStatus.RUNNING
    cols: int = 80
    rows: int = 24
    history: bytearray = field(default_factory=bytearray)
    title: str = ""
    exit_code: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    role: str = ""  # e.g. "architect", "reviewer", "coder"
    env: Dict[str, str] = field(default_factory=dict)  # custom env vars

    # Runtime: not serialized
    clients: Set[asyncio.Queue] = field(default_factory=set, repr=False)
    _read_task: Optional[asyncio.Task] = field(default=None, repr=False)

    MAX_HISTORY = 1024 * 1024  # 1MB
    TRIM_HISTORY = 1024 * 512  # 512KB

    def trim_history(self) -> None:
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.TRIM_HISTORY :]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "status": self.status.value,
            "cols": self.cols,
            "rows": self.rows,
            "title": self.title,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "history_size": len(self.history),
            "role": self.role,
        }


@dataclass
class TmuxWindow:
    """A window containing one or more panes arranged in a layout tree."""

    window_id: str = field(default_factory=lambda: f"win_{uuid4().hex[:8]}")
    window_index: int = 0
    name: str = ""
    layout: LayoutNode = field(default_factory=lambda: LayoutNode(type=LayoutType.LEAF))
    panes: Dict[str, TmuxPane] = field(default_factory=dict)
    active_pane_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "window_index": self.window_index,
            "name": self.name,
            "layout": self.layout.to_dict(),
            "panes": {pid: p.to_dict() for pid, p in self.panes.items()},
            "active_pane_id": self.active_pane_id,
        }


@dataclass
class TmuxSession:
    """A tmux session containing one or more windows."""

    session_id: str = field(default_factory=lambda: f"sess_{uuid4().hex[:8]}")
    name: str = ""
    created_at: float = field(default_factory=time.time)
    windows: Dict[str, TmuxWindow] = field(default_factory=dict)
    active_window_id: str = ""
    next_window_index: int = 0

    # Runtime: client broadcast queues
    client_queues: Set[asyncio.Queue] = field(default_factory=set, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "windows": {wid: w.to_dict() for wid, w in self.windows.items()},
            "active_window_id": self.active_window_id,
            "active_clients": len(self.client_queues),
        }
