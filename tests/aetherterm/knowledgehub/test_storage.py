"""Tests for LocalStorage."""

import json

import pytest

from aetherterm.knowledgehub.models import SkillMetadata, SkillScope
from aetherterm.knowledgehub.storage import LocalStorage, PLATFORM_TENANT


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(str(tmp_path / "skills"))


def test_save_and_load_metadata(storage):
    meta = SkillMetadata(
        skill_id="test-skill",
        tenant_id="t1",
        scope=SkillScope.TENANT,
        name="Test",
    )
    storage.save_metadata(meta)
    loaded = storage.load_metadata("t1", "test-skill")
    assert loaded is not None
    assert loaded.skill_id == "test-skill"
    assert loaded.tenant_id == "t1"
    assert loaded.name == "Test"


def test_load_nonexistent(storage):
    assert storage.load_metadata("t1", "nope") is None


def test_delete_skill(storage):
    meta = SkillMetadata(skill_id="del-me", tenant_id="t1", name="Del")
    storage.save_metadata(meta)
    assert storage.delete_skill("t1", "del-me") is True
    assert storage.load_metadata("t1", "del-me") is None


def test_delete_nonexistent(storage):
    assert storage.delete_skill("t1", "nope") is False


def test_store_files(storage):
    meta = SkillMetadata(skill_id="s1", tenant_id="t1", name="S1")
    storage.save_metadata(meta)
    vdir = storage.store_files("t1", "s1", 1, {"SKILL.md": b"# Hello"})
    assert (vdir / "SKILL.md").read_bytes() == b"# Hello"


def test_list_skills(storage):
    for i in range(3):
        meta = SkillMetadata(skill_id=f"s{i}", tenant_id="t1", name=f"Skill {i}")
        storage.save_metadata(meta)
    skills = storage.list_skills("t1")
    assert len(skills) == 3
    assert {s.skill_id for s in skills} == {"s0", "s1", "s2"}


def test_list_skills_empty(storage):
    assert storage.list_skills("nonexistent") == []


def test_get_skill_files_dir(storage):
    meta = SkillMetadata(skill_id="s1", tenant_id="t1", name="S1")
    storage.save_metadata(meta)
    storage.store_files("t1", "s1", 1, {"SKILL.md": b"# Test"})
    d = storage.get_skill_files_dir("t1", "s1")
    assert d is not None
    assert (d / "SKILL.md").exists()


def test_bootstrap_platform_skills(storage, tmp_path):
    src = tmp_path / "platform"
    src.mkdir()
    skill_dir = src / "my-builtin"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Built-in")

    count = storage.bootstrap_platform_skills(str(src))
    assert count == 1

    meta = storage.load_metadata(PLATFORM_TENANT, "my-builtin")
    assert meta is not None
    assert meta.scope == SkillScope.PLATFORM

    # Second bootstrap is idempotent
    assert storage.bootstrap_platform_skills(str(src)) == 0
