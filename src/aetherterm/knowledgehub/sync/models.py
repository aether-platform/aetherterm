"""Data models for sync connections."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SyncStatus(str, enum.Enum):
    """Lifecycle status of a sync connection."""

    IDLE = "idle"
    SYNCING = "syncing"
    PAUSED = "paused"
    ERROR = "error"


class SyncConnection(BaseModel):
    """Represents a configured connection to an external data source."""

    id: str
    provider: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    status: SyncStatus = SyncStatus.IDLE
    schedule: str = ""  # cron expression or empty for manual
    last_sync: str = ""
    doc_count: int = 0
    tenant_id: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error_message: str = ""
