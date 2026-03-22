"""Local filesystem storage backend for SkillRegistry.

Layout:
    {base_dir}/
    ├── _platform/
    │   └── {skill_id}/
    │       ├── SKILL.md
    │       └── metadata.json
    └── {tenant_id}/
        └── {skill_id}/
            ├── v{N}/
            │   ├── SKILL.md
            │   └── [additional files]
            └── metadata.json
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from aetherterm.knowledgehub.models import SkillMetadata, SkillScope

log = logging.getLogger("knowledgehub.storage")

PLATFORM_TENANT = "_platform"


class LocalStorage:
    """File-system based skill storage."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    # ---- helpers ----

    def _tenant_dir(self, tenant_id: str) -> Path:
        return self._base / tenant_id

    def _skill_dir(self, tenant_id: str, skill_id: str) -> Path:
        return self._tenant_dir(tenant_id) / skill_id

    def _metadata_path(self, tenant_id: str, skill_id: str) -> Path:
        return self._skill_dir(tenant_id, skill_id) / "metadata.json"

    def _version_dir(self, tenant_id: str, skill_id: str, version: int) -> Path:
        return self._skill_dir(tenant_id, skill_id) / f"v{version}"

    def _latest_files_dir(self, tenant_id: str, skill_id: str, version: int) -> Path:
        """Return the directory containing the actual skill files."""
        vdir = self._version_dir(tenant_id, skill_id, version)
        if vdir.is_dir():
            return vdir
        # platform skills have no version subdirectory
        return self._skill_dir(tenant_id, skill_id)

    # ---- CRUD ----

    def save_metadata(self, meta: SkillMetadata) -> None:
        path = self._metadata_path(meta.tenant_id, meta.skill_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta.model_dump(), indent=2))

    def load_metadata(self, tenant_id: str, skill_id: str) -> SkillMetadata | None:
        path = self._metadata_path(tenant_id, skill_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return SkillMetadata(**data)

    def delete_skill(self, tenant_id: str, skill_id: str) -> bool:
        d = self._skill_dir(tenant_id, skill_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True

    def store_files(
        self, tenant_id: str, skill_id: str, version: int, files: dict[str, bytes]
    ) -> Path:
        """Store uploaded files under the version directory.

        Returns the version directory path.
        """
        vdir = self._version_dir(tenant_id, skill_id, version)
        vdir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (vdir / name).write_bytes(content)
        return vdir

    def list_skills(self, tenant_id: str) -> list[SkillMetadata]:
        """List all skills for a tenant."""
        result: list[SkillMetadata] = []
        tdir = self._tenant_dir(tenant_id)
        if not tdir.is_dir():
            return result
        for child in sorted(tdir.iterdir()):
            meta_path = child / "metadata.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text())
                    result.append(SkillMetadata(**data))
                except Exception:
                    log.warning("Skipping corrupt metadata: %s", meta_path)
        return result

    def get_skill_files_dir(self, tenant_id: str, skill_id: str) -> Path | None:
        """Return the path to the latest version's files directory."""
        meta = self.load_metadata(tenant_id, skill_id)
        if meta is None:
            return None
        d = self._latest_files_dir(tenant_id, skill_id, meta.version)
        return d if d.is_dir() else None

    # ---- platform skill bootstrap ----

    def bootstrap_platform_skills(self, source_dir: str) -> int:
        """Copy built-in skills from source_dir into storage.

        Returns the number of skills bootstrapped.
        """
        src = Path(source_dir)
        if not src.is_dir():
            return 0

        count = 0
        for skill_dir in sorted(src.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_id = skill_dir.name
            existing = self.load_metadata(PLATFORM_TENANT, skill_id)
            if existing is not None:
                continue  # already registered

            # Build metadata from SKILL.md front-matter or defaults
            dest = self._skill_dir(PLATFORM_TENANT, skill_id)
            dest.mkdir(parents=True, exist_ok=True)
            for f in skill_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / f.name)

            meta = SkillMetadata(
                skill_id=skill_id,
                tenant_id=PLATFORM_TENANT,
                scope=SkillScope.PLATFORM,
                name=skill_id,
                description=f"Built-in platform skill: {skill_id}",
                version=1,
            )
            self.save_metadata(meta)
            count += 1
            log.info("Bootstrapped platform skill: %s", skill_id)

        return count
