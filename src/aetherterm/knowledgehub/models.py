"""Pydantic models for SkillRegistry."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class SkillScope(str, Enum):
    PLATFORM = "platform"
    TENANT = "tenant"
    PUBLIC = "public"


class SkillMetadata(BaseModel):
    """Persisted skill metadata."""

    skill_id: str
    tenant_id: str = "_platform"
    scope: SkillScope = SkillScope.TENANT
    name: str
    description: str = ""
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    context: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# --- Request / Response models ---


class RegisterSkillRequest(BaseModel):
    """JSON part of the multipart skill registration."""

    skill_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    context: str = ""
    env: dict[str, str] = Field(default_factory=dict)


class UpdateSkillRequest(BaseModel):
    """Fields that can be updated (creates a new version)."""

    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    context: str | None = None
    env: dict[str, str] | None = None


class SkillResponse(BaseModel):
    skill_id: str
    tenant_id: str
    scope: SkillScope
    name: str
    description: str
    version: int
    tags: list[str]
    context: str
    env: dict[str, str]
    created_at: str
    updated_at: str


class ResolveRequest(BaseModel):
    skill_ids: list[str]


class ResolvedSkill(BaseModel):
    """A single resolved skill ready for injection."""

    skill_id: str
    provider: str
    skill_dir: str
    context: str
    env: dict[str, str]


class ResolveResponse(BaseModel):
    resolved: list[ResolvedSkill]
    missing: list[str] = Field(default_factory=list)
