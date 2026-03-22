"""Tests for SkillRegistry models."""

from aetherterm.knowledgehub.models import (
    RegisterSkillRequest,
    ResolveRequest,
    ResolveResponse,
    ResolvedSkill,
    SkillMetadata,
    SkillScope,
    UpdateSkillRequest,
)


def test_skill_metadata_defaults():
    meta = SkillMetadata(skill_id="test", name="Test Skill")
    assert meta.tenant_id == "_platform"
    assert meta.scope == SkillScope.TENANT
    assert meta.version == 1
    assert meta.tags == []
    assert meta.env == {}
    assert meta.created_at
    assert meta.updated_at


def test_skill_metadata_full():
    meta = SkillMetadata(
        skill_id="my-skill",
        tenant_id="tenant-1",
        scope=SkillScope.TENANT,
        name="My Skill",
        description="A test skill",
        version=3,
        tags=["python", "testing"],
        context="Use this for testing",
        env={"FOO": "bar"},
    )
    assert meta.skill_id == "my-skill"
    assert meta.tenant_id == "tenant-1"
    assert meta.scope == SkillScope.TENANT
    assert meta.version == 3
    assert meta.tags == ["python", "testing"]


def test_register_skill_request():
    req = RegisterSkillRequest(skill_id="s1", name="Skill One")
    assert req.skill_id == "s1"
    assert req.description == ""
    assert req.tags == []


def test_update_skill_request_partial():
    req = UpdateSkillRequest(name="Updated")
    assert req.name == "Updated"
    assert req.description is None
    assert req.tags is None


def test_resolve_request():
    req = ResolveRequest(skill_ids=["a", "b"])
    assert req.skill_ids == ["a", "b"]


def test_resolve_response():
    resp = ResolveResponse(
        resolved=[
            ResolvedSkill(
                skill_id="a",
                provider="a",
                skill_dir="/tmp/a",
                context="ctx",
                env={"X": "1"},
            )
        ],
        missing=["b"],
    )
    assert len(resp.resolved) == 1
    assert resp.missing == ["b"]
