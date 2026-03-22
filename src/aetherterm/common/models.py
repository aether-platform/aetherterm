"""Shared Pydantic models for AetherTerm components.

Canonical definitions for data objects passed between ControlServer,
AgentServer, and AgentShell.  All models use Pydantic v2 conventions.
"""
from __future__ import annotations

import time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Session mapping models (used by NATSController & NATSControlBridge)
# ---------------------------------------------------------------------------

class PaneDetail(BaseModel):
    """Detail information for a single pane."""

    pane_id: str
    status: str = "running"  # running / exited / blocked
    role: str = ""
    title: str = ""
    cols: int = 80
    rows: int = 24
    exit_code: Optional[int] = None
    created_at: float = Field(default_factory=time.time)


class WindowDetail(BaseModel):
    """Detail information for a single window."""

    window_id: str
    name: str = ""
    active_pane_id: str = ""
    panes: List[PaneDetail] = Field(default_factory=list)


class PtySessionInfo(BaseModel):
    """A PTY session managed by an AgentServer."""

    session_id: str
    agent_server_id: str
    name: str = ""
    user_info: Dict = Field(default_factory=dict)
    pane_ids: List[str] = Field(default_factory=list)
    shell_ids: List[str] = Field(default_factory=list)
    windows: List[WindowDetail] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    last_activity: float = Field(default_factory=time.time)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class ShellInfo(BaseModel):
    """An AgentShell instance attached to a PTY session."""

    shell_id: str
    session_id: str
    agent_server_id: str
    registered_at: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# ControlServer models
# ---------------------------------------------------------------------------

class BlockCommand(BaseModel):
    """Block command issued by admin or auto-detection."""

    block_id: str
    block_type: Literal["admin_initiated", "auto_detected", "emergency"]
    reason: str
    admin_user: Optional[str] = None
    affected_sessions: List[str] = Field(default_factory=list)
    timestamp: str = ""
    expires_at: Optional[str] = None


class SessionInfo(BaseModel):
    """Session information tracked by CentralController."""

    session_id: str
    agent_server_id: str
    user_info: Dict = Field(default_factory=dict)
    created_at: str = ""
    last_activity: str = ""
    is_blocked: bool = False
    block_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Log analysis models
# ---------------------------------------------------------------------------

class LogAnalysisResult(BaseModel):
    """Result of LLM-based log analysis."""

    session_id: str
    analysis_type: str = "anomaly"  # "anomaly" / "summary" / "both"
    anomalies: List[Dict] = Field(default_factory=list)
    summary: str = ""
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    timestamp: str = ""
    model_used: str = ""
    token_usage: Dict = Field(default_factory=dict)
