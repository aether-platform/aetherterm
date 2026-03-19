"""Shared pane and layout models used by both agentserver and agiterm.

These are service-agnostic data structures. Service-specific models
(TmuxPane, TmuxWindow, TmuxSession, SDKSession) extend or wrap these.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class PaneStatus(str, Enum):
    RUNNING = "running"
    EXITED = "exited"
    BLOCKED = "blocked"


class LayoutType(str, Enum):
    LEAF = "leaf"
    HSPLIT = "hsplit"
    VSPLIT = "vsplit"


@dataclass
class LayoutNode:
    """Binary tree node for pane layout.

    For leaf nodes: pane_id is set, children is empty.
    For split nodes: two children with a ratio.
    """

    type: LayoutType = LayoutType.LEAF
    pane_id: Optional[str] = None
    children: List[LayoutNode] = field(default_factory=list)
    ratio: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type.value, "ratio": self.ratio}
        if self.pane_id is not None:
            d["pane_id"] = self.pane_id
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LayoutNode:
        children = [cls.from_dict(c) for c in data.get("children", [])]
        return cls(
            type=LayoutType(data["type"]),
            pane_id=data.get("pane_id"),
            children=children,
            ratio=data.get("ratio", 0.5),
        )

    def find_leaf(self, pane_id: str) -> Optional[LayoutNode]:
        """Find a leaf node by pane_id."""
        if self.type == LayoutType.LEAF and self.pane_id == pane_id:
            return self
        for child in self.children:
            result = child.find_leaf(pane_id)
            if result is not None:
                return result
        return None

    def find_parent(self, pane_id: str) -> Optional[LayoutNode]:
        """Find the parent node of a leaf with the given pane_id."""
        for child in self.children:
            if child.type == LayoutType.LEAF and child.pane_id == pane_id:
                return self
            result = child.find_parent(pane_id)
            if result is not None:
                return result
        return None

    def collect_pane_ids(self) -> List[str]:
        """Collect all pane IDs in traversal order."""
        if self.type == LayoutType.LEAF:
            return [self.pane_id] if self.pane_id else []
        ids: List[str] = []
        for child in self.children:
            ids.extend(child.collect_pane_ids())
        return ids


@dataclass
class PaneConfig:
    """Configuration for spawning a new pane."""

    cmd: List[str] = field(default_factory=lambda: ["/bin/bash"])
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    cols: int = 80
    rows: int = 24
    role: str = ""
    title: str = ""


@dataclass
class PaneInfo:
    """A pane with its PTY session reference.

    This is the shared model. Service-specific models (TmuxPane, agiterm.Pane)
    can wrap or extend this.
    """

    pane_id: str = field(default_factory=lambda: f"pane_{uuid4().hex[:8]}")
    status: PaneStatus = PaneStatus.RUNNING
    config: PaneConfig = field(default_factory=PaneConfig)
    created_at: float = field(default_factory=time.time)
    exit_code: Optional[int] = None
    # PTY session ID — used to look up the PTYSession in PTYManager
    pty_session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "status": self.status.value,
            "role": self.config.role,
            "title": self.config.title,
            "cols": self.config.cols,
            "rows": self.config.rows,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
        }
