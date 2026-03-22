"""Tests for SkillRegistry REST API routes."""

import json

import pytest
from fastapi.testclient import TestClient

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.server import create_app
from aetherterm.knowledgehub.storage import LocalStorage


@pytest.fixture
def setup(tmp_path):
    storage = LocalStorage(str(tmp_path / "skills"))
    manager = SkillRegistryManager(storage)
    auth = APIKeyAuthenticator()
    auth.register_tenant(tenant_id="t1", name="Test Tenant", api_key="test-key")
    app = create_app(auth=auth, manager=manager)
    client = TestClient(app)
    return client, manager, storage


@pytest.fixture
def client(setup):
    return setup[0]


HEADERS = {"X-API-Key": "test-key"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_skills_empty(client):
    r = client.get("/api/v1/skills", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


def test_register_skill(client):
    metadata = json.dumps({"skill_id": "my-skill", "name": "My Skill", "description": "A test"})
    r = client.post(
        "/api/v1/skills",
        headers=HEADERS,
        data={"metadata": metadata},
        files=[("files", ("SKILL.md", b"# My Skill", "text/markdown"))],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["skill_id"] == "my-skill"
    assert body["name"] == "My Skill"
    assert body["version"] == 1
    assert body["tenant_id"] == "t1"


def test_register_duplicate(client):
    metadata = json.dumps({"skill_id": "dup", "name": "Dup"})
    client.post("/api/v1/skills", headers=HEADERS, data={"metadata": metadata})
    r = client.post("/api/v1/skills", headers=HEADERS, data={"metadata": metadata})
    assert r.status_code == 409


def test_get_skill(client):
    metadata = json.dumps({"skill_id": "s1", "name": "S1"})
    client.post("/api/v1/skills", headers=HEADERS, data={"metadata": metadata})
    r = client.get("/api/v1/skills/s1", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["skill_id"] == "s1"


def test_get_skill_not_found(client):
    r = client.get("/api/v1/skills/nope", headers=HEADERS)
    assert r.status_code == 404


def test_update_skill(client):
    metadata = json.dumps({"skill_id": "up", "name": "Original"})
    client.post(
        "/api/v1/skills",
        headers=HEADERS,
        data={"metadata": metadata},
        files=[("files", ("SKILL.md", b"# V1", "text/markdown"))],
    )

    update_meta = json.dumps({"name": "Updated"})
    r = client.put(
        "/api/v1/skills/up",
        headers=HEADERS,
        data={"metadata": update_meta},
        files=[("files", ("SKILL.md", b"# V2", "text/markdown"))],
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["name"] == "Updated"


def test_delete_skill(client):
    metadata = json.dumps({"skill_id": "del", "name": "Del"})
    client.post("/api/v1/skills", headers=HEADERS, data={"metadata": metadata})
    r = client.delete("/api/v1/skills/del", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


def test_delete_not_found(client):
    r = client.delete("/api/v1/skills/nope", headers=HEADERS)
    assert r.status_code == 404


def test_resolve_skills(client):
    # Register a skill with files
    metadata = json.dumps({
        "skill_id": "res",
        "name": "Resolvable",
        "context": "extra context",
        "env": {"KEY": "val"},
    })
    client.post(
        "/api/v1/skills",
        headers=HEADERS,
        data={"metadata": metadata},
        files=[("files", ("SKILL.md", b"# Res", "text/markdown"))],
    )

    r = client.post(
        "/api/v1/skills/resolve",
        headers=HEADERS,
        json={"skill_ids": ["res", "missing"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["resolved"]) == 1
    assert body["resolved"][0]["skill_id"] == "res"
    assert body["resolved"][0]["context"] == "extra context"
    assert body["resolved"][0]["env"] == {"KEY": "val"}
    assert body["missing"] == ["missing"]


def test_download_skill(client):
    metadata = json.dumps({"skill_id": "dl", "name": "Download"})
    client.post(
        "/api/v1/skills",
        headers=HEADERS,
        data={"metadata": metadata},
        files=[("files", ("SKILL.md", b"# Download test", "text/markdown"))],
    )

    r = client.get("/api/v1/skills/dl/download", headers=HEADERS)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"


def test_unauthorized(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 401

    r = client.get("/api/v1/skills", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_list_skills_after_register(client):
    for i in range(3):
        metadata = json.dumps({"skill_id": f"s{i}", "name": f"Skill {i}"})
        client.post("/api/v1/skills", headers=HEADERS, data={"metadata": metadata})

    r = client.get("/api/v1/skills", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 3
