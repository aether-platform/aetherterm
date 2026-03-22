"""Tests for SkillRegistryManager."""

import pytest

from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.models import SkillScope, UpdateSkillRequest
from aetherterm.knowledgehub.storage import LocalStorage, PLATFORM_TENANT


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(str(tmp_path / "skills"))


@pytest.fixture
def manager(storage):
    return SkillRegistryManager(storage)


def test_register_and_get(manager):
    meta = manager.register_skill(
        tenant_id="t1",
        skill_id="my-skill",
        name="My Skill",
        description="desc",
        tags=["python"],
        context="Use python",
        env={"PY": "1"},
        files={"SKILL.md": b"# My Skill"},
    )
    assert meta.skill_id == "my-skill"
    assert meta.version == 1

    loaded = manager.get_skill("t1", "my-skill")
    assert loaded is not None
    assert loaded.name == "My Skill"


def test_register_duplicate_raises(manager):
    manager.register_skill(tenant_id="t1", skill_id="dup", name="Dup")
    with pytest.raises(ValueError, match="already exists"):
        manager.register_skill(tenant_id="t1", skill_id="dup", name="Dup2")


def test_update_creates_new_version(manager):
    manager.register_skill(
        tenant_id="t1",
        skill_id="s1",
        name="S1",
        files={"SKILL.md": b"v1"},
    )
    updated = manager.update_skill(
        tenant_id="t1",
        skill_id="s1",
        update=UpdateSkillRequest(name="S1 Updated", tags=["new"]),
        files={"SKILL.md": b"v2"},
    )
    assert updated.version == 2
    assert updated.name == "S1 Updated"
    assert updated.tags == ["new"]


def test_update_nonexistent_raises(manager):
    with pytest.raises(ValueError, match="not found"):
        manager.update_skill("t1", "nope", UpdateSkillRequest(name="X"))


def test_delete(manager):
    manager.register_skill(tenant_id="t1", skill_id="del", name="Del")
    assert manager.delete_skill("t1", "del") is True
    assert manager.get_skill("t1", "del") is None


def test_delete_nonexistent(manager):
    assert manager.delete_skill("t1", "nope") is False


def test_list_skills_includes_platform(manager, storage):
    # Register a platform skill directly
    from aetherterm.knowledgehub.models import SkillMetadata

    platform_meta = SkillMetadata(
        skill_id="builtin",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Built-in",
    )
    storage.save_metadata(platform_meta)

    manager.register_skill(tenant_id="t1", skill_id="custom", name="Custom")

    skills = manager.list_skills("t1")
    ids = {s.skill_id for s in skills}
    assert "custom" in ids
    assert "builtin" in ids


def test_list_tenant_shadows_platform(manager, storage):
    """Tenant skill with same ID shadows platform skill."""
    from aetherterm.knowledgehub.models import SkillMetadata

    platform_meta = SkillMetadata(
        skill_id="shared",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Platform Version",
    )
    storage.save_metadata(platform_meta)

    manager.register_skill(tenant_id="t1", skill_id="shared", name="Tenant Version")

    skills = manager.list_skills("t1")
    shared_skills = [s for s in skills if s.skill_id == "shared"]
    assert len(shared_skills) == 1
    assert shared_skills[0].tenant_id == "t1"


def test_resolve_tenant_and_platform(manager, storage):
    from aetherterm.knowledgehub.models import SkillMetadata

    # Platform skill with files
    platform_meta = SkillMetadata(
        skill_id="p-skill",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Platform",
        context="platform context",
    )
    storage.save_metadata(platform_meta)
    storage.store_files(PLATFORM_TENANT, "p-skill", 1, {"SKILL.md": b"# Platform"})

    # Tenant skill with files
    manager.register_skill(
        tenant_id="t1",
        skill_id="t-skill",
        name="Tenant",
        context="tenant context",
        files={"SKILL.md": b"# Tenant"},
    )

    resolved, missing = manager.resolve("t1", ["t-skill", "p-skill", "unknown"])
    assert len(resolved) == 2
    assert missing == ["unknown"]

    ids = {r.skill_id for r in resolved}
    assert "t-skill" in ids
    assert "p-skill" in ids


def test_resolve_tenant_shadows_platform(manager, storage):
    """resolve prefers tenant scope over platform."""
    from aetherterm.knowledgehub.models import SkillMetadata

    platform_meta = SkillMetadata(
        skill_id="shadow",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Platform",
    )
    storage.save_metadata(platform_meta)
    storage.store_files(PLATFORM_TENANT, "shadow", 1, {"SKILL.md": b"# P"})

    manager.register_skill(
        tenant_id="t1",
        skill_id="shadow",
        name="Tenant",
        context="tenant ver",
        files={"SKILL.md": b"# T"},
    )

    resolved, missing = manager.resolve("t1", ["shadow"])
    assert len(resolved) == 1
    assert resolved[0].context == "tenant ver"


def test_cannot_update_platform_skill(manager, storage):
    from aetherterm.knowledgehub.models import SkillMetadata

    meta = SkillMetadata(
        skill_id="builtin",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Built-in",
    )
    storage.save_metadata(meta)

    with pytest.raises(ValueError, match="platform"):
        manager.update_skill(PLATFORM_TENANT, "builtin", UpdateSkillRequest(name="Hacked"))


def test_cannot_delete_platform_skill(manager, storage):
    from aetherterm.knowledgehub.models import SkillMetadata

    meta = SkillMetadata(
        skill_id="builtin",
        tenant_id=PLATFORM_TENANT,
        scope=SkillScope.PLATFORM,
        name="Built-in",
    )
    storage.save_metadata(meta)

    with pytest.raises(ValueError, match="platform"):
        manager.delete_skill(PLATFORM_TENANT, "builtin")
