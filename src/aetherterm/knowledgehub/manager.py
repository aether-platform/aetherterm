"""SkillRegistryManager — core business logic for skill CRUD and resolution."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone

from aetherterm.knowledgehub.models import (
    ResolvedSkill,
    SkillMetadata,
    SkillScope,
    UpdateSkillRequest,
)
from aetherterm.knowledgehub.storage import PLATFORM_TENANT, LocalStorage

log = logging.getLogger("knowledgehub.manager")


class SkillRegistryManager:
    """Manages skill lifecycle: register, update, delete, list, resolve."""

    def __init__(self, storage: LocalStorage) -> None:
        self._storage = storage

    # ---- CRUD ----

    def register_skill(
        self,
        tenant_id: str,
        skill_id: str,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        context: str = "",
        env: dict[str, str] | None = None,
        files: dict[str, bytes] | None = None,
    ) -> SkillMetadata:
        """Register a new skill for a tenant."""
        existing = self._storage.load_metadata(tenant_id, skill_id)
        if existing is not None:
            raise ValueError(f"Skill '{skill_id}' already exists for tenant '{tenant_id}'")

        now = datetime.now(timezone.utc).isoformat()
        meta = SkillMetadata(
            skill_id=skill_id,
            tenant_id=tenant_id,
            scope=SkillScope.TENANT,
            name=name,
            description=description,
            version=1,
            tags=tags or [],
            context=context,
            env=env or {},
            created_at=now,
            updated_at=now,
        )
        self._storage.save_metadata(meta)

        if files:
            self._storage.store_files(tenant_id, skill_id, 1, files)

        log.info("Registered skill %s for tenant %s", skill_id, tenant_id)
        return meta

    def get_skill(self, tenant_id: str, skill_id: str) -> SkillMetadata | None:
        """Get skill metadata.  Falls back to platform scope."""
        meta = self._storage.load_metadata(tenant_id, skill_id)
        if meta is None and tenant_id != PLATFORM_TENANT:
            meta = self._storage.load_metadata(PLATFORM_TENANT, skill_id)
        return meta

    def update_skill(
        self,
        tenant_id: str,
        skill_id: str,
        update: UpdateSkillRequest,
        files: dict[str, bytes] | None = None,
    ) -> SkillMetadata:
        """Update a tenant skill (creates a new version)."""
        meta = self._storage.load_metadata(tenant_id, skill_id)
        if meta is None:
            raise ValueError(f"Skill '{skill_id}' not found for tenant '{tenant_id}'")
        if meta.scope == SkillScope.PLATFORM:
            raise ValueError("Cannot update platform skills")

        new_version = meta.version + 1
        if update.name is not None:
            meta.name = update.name
        if update.description is not None:
            meta.description = update.description
        if update.tags is not None:
            meta.tags = update.tags
        if update.context is not None:
            meta.context = update.context
        if update.env is not None:
            meta.env = update.env
        meta.version = new_version
        meta.updated_at = datetime.now(timezone.utc).isoformat()

        self._storage.save_metadata(meta)

        if files:
            self._storage.store_files(tenant_id, skill_id, new_version, files)

        log.info("Updated skill %s to v%d for tenant %s", skill_id, new_version, tenant_id)
        return meta

    def delete_skill(self, tenant_id: str, skill_id: str) -> bool:
        meta = self._storage.load_metadata(tenant_id, skill_id)
        if meta is None:
            return False
        if meta.scope == SkillScope.PLATFORM:
            raise ValueError("Cannot delete platform skills")
        return self._storage.delete_skill(tenant_id, skill_id)

    def list_skills(self, tenant_id: str) -> list[SkillMetadata]:
        """List tenant skills + platform skills."""
        tenant_skills = self._storage.list_skills(tenant_id)
        platform_skills = self._storage.list_skills(PLATFORM_TENANT)

        # Deduplicate: tenant skills shadow platform skills of the same id
        tenant_ids = {s.skill_id for s in tenant_skills}
        combined = list(tenant_skills)
        for ps in platform_skills:
            if ps.skill_id not in tenant_ids:
                combined.append(ps)

        return combined

    # ---- resolve ----

    def resolve(self, tenant_id: str, skill_ids: list[str]) -> tuple[list[ResolvedSkill], list[str]]:
        """Resolve skill_ids to SkillSource-compatible data.

        Lookup order: tenant scope → platform fallback.
        Returns (resolved, missing).
        """
        resolved: list[ResolvedSkill] = []
        missing: list[str] = []

        for sid in skill_ids:
            meta = self._storage.load_metadata(tenant_id, sid)
            if meta is None and tenant_id != PLATFORM_TENANT:
                meta = self._storage.load_metadata(PLATFORM_TENANT, sid)

            if meta is None:
                missing.append(sid)
                continue

            files_dir = self._storage.get_skill_files_dir(meta.tenant_id, sid)
            if files_dir is None:
                missing.append(sid)
                continue

            resolved.append(
                ResolvedSkill(
                    skill_id=sid,
                    provider=sid,
                    skill_dir=str(files_dir),
                    context=meta.context,
                    env=meta.env,
                )
            )

        return resolved, missing
