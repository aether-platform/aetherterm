"""Integration tests: KnowledgeHub → agiterm session creation flow.

Verifies the end-to-end flow:
1. KnowledgeHub server starts and can register/resolve skills
2. CreateSessionRequest accepts skill_ids
3. KnowledgeHubClient can resolve skills from the server
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aetherterm.agiterm.api.routes import CreateSessionRequest
from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.agiterm.sessions.manager import SkillSource
from aetherterm.knowledgehub.client import KnowledgeHubClient
from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.server import create_app
from aetherterm.knowledgehub.storage import LocalStorage


HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def hub_setup(tmp_path):
    """Create a fully wired KnowledgeHub app with TestClient."""
    storage = LocalStorage(str(tmp_path / "skills"))
    manager = SkillRegistryManager(storage)
    auth = APIKeyAuthenticator()
    auth.register_tenant(tenant_id="t1", name="Test Tenant", api_key="test-key")
    app = create_app(auth=auth, manager=manager)
    client = TestClient(app)
    return client, manager, storage, auth


@pytest.fixture
def hub_client(hub_setup):
    return hub_setup[0]


def _make_mock_httpx_response(data: dict) -> MagicMock:
    """Create a mock httpx.Response that works with async context manager.

    httpx.Response.json() and .raise_for_status() are sync methods,
    so we use MagicMock (not AsyncMock) for them.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = data
    mock_response.raise_for_status.return_value = None
    return mock_response


def _make_mock_async_client(mock_response: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient with async context manager support."""
    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = False
    return mock_http


# ---------------------------------------------------------------------------
# 1. KnowledgeHub server: register + resolve round-trip
# ---------------------------------------------------------------------------


class TestKnowledgeHubRegisterResolve:
    """Full register → resolve flow through the HTTP API."""

    def test_register_and_resolve_skill(self, hub_setup):
        client, manager, storage, auth = hub_setup

        # Register a skill with files, context, and env
        metadata = json.dumps({
            "skill_id": "secretary",
            "name": "Secretary Skill",
            "description": "AI assistant for scheduling",
            "context": "You are a scheduling assistant.",
            "env": {"CALENDAR_API": "https://cal.example.com"},
        })
        r = client.post(
            "/api/v1/skills",
            headers=HEADERS,
            data={"metadata": metadata},
            files=[
                ("files", ("SKILL.md", b"# Secretary\nScheduling assistant", "text/markdown")),
                ("files", ("guide.txt", b"Use ISO-8601 dates", "text/plain")),
            ],
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["skill_id"] == "secretary"
        assert body["tenant_id"] == "t1"
        assert body["version"] == 1

        # Resolve the registered skill
        r = client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": ["secretary"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["resolved"]) == 1
        assert data["missing"] == []

        resolved = data["resolved"][0]
        assert resolved["skill_id"] == "secretary"
        assert resolved["provider"] == "secretary"
        assert resolved["context"] == "You are a scheduling assistant."
        assert resolved["env"] == {"CALENDAR_API": "https://cal.example.com"}
        # skill_dir should be a real path on disk
        assert resolved["skill_dir"]

    def test_resolve_with_missing_skills(self, hub_client):
        """Resolve returns missing list for unknown skill_ids."""
        r = hub_client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": ["nonexistent-a", "nonexistent-b"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["resolved"] == []
        assert set(data["missing"]) == {"nonexistent-a", "nonexistent-b"}

    def test_resolve_mixed_found_and_missing(self, hub_setup):
        client = hub_setup[0]

        # Register one skill
        metadata = json.dumps({"skill_id": "found-skill", "name": "Found"})
        client.post(
            "/api/v1/skills",
            headers=HEADERS,
            data={"metadata": metadata},
            files=[("files", ("SKILL.md", b"# Found", "text/markdown"))],
        )

        # Resolve with one existing and one missing
        r = client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": ["found-skill", "ghost"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["resolved"]) == 1
        assert data["resolved"][0]["skill_id"] == "found-skill"
        assert data["missing"] == ["ghost"]


# ---------------------------------------------------------------------------
# 2. CreateSessionRequest accepts skill_ids
# ---------------------------------------------------------------------------


class TestCreateSessionRequestSkillIds:
    """Verify the Pydantic model accepts skill_ids field."""

    def test_default_empty(self):
        req = CreateSessionRequest(user_id="u1")
        assert req.skill_ids == []

    def test_with_skill_ids(self):
        req = CreateSessionRequest(user_id="u1", skill_ids=["sk-a", "sk-b"])
        assert req.skill_ids == ["sk-a", "sk-b"]

    def test_serialization_includes_skill_ids(self):
        req = CreateSessionRequest(user_id="u1", skill_ids=["sk-x"])
        data = req.model_dump()
        assert "skill_ids" in data
        assert data["skill_ids"] == ["sk-x"]


# ---------------------------------------------------------------------------
# 3. KnowledgeHubClient.resolve() returns SkillSource objects
# ---------------------------------------------------------------------------


class TestKnowledgeHubClientResolve:
    """Test KnowledgeHubClient.resolve() against a real KnowledgeHub server.

    Uses httpx mocking to route client HTTP calls through the TestClient,
    verifying that KnowledgeHubClient correctly maps server responses to
    SkillSource dataclass instances.
    """

    @pytest.mark.asyncio
    async def test_resolve_returns_skill_sources(self, hub_setup):
        client, manager, storage, auth = hub_setup

        # Register a skill via TestClient
        metadata = json.dumps({
            "skill_id": "coder",
            "name": "Coder Skill",
            "context": "You write Python code.",
            "env": {"LANG": "python"},
        })
        r = client.post(
            "/api/v1/skills",
            headers=HEADERS,
            data={"metadata": metadata},
            files=[("files", ("SKILL.md", b"# Coder", "text/markdown"))],
        )
        assert r.status_code == 201

        # Get the expected resolve response from TestClient
        r = client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": ["coder"]},
        )
        assert r.status_code == 200
        expected_response = r.json()

        # Test KnowledgeHubClient.resolve() by mocking httpx
        hub_client = KnowledgeHubClient(base_url="http://knowledgehub:9090")
        mock_response = _make_mock_httpx_response(expected_response)
        mock_http = _make_mock_async_client(mock_response)

        with patch("aetherterm.knowledgehub.client.httpx.AsyncClient", return_value=mock_http):
            sources = await hub_client.resolve(tenant_id="t1", skill_ids=["coder"])

        assert len(sources) == 1
        src = sources[0]
        assert isinstance(src, SkillSource)
        assert src.provider == "coder"
        assert src.context == "You write Python code."
        assert src.env == {"LANG": "python"}
        assert src.skill_dir  # non-empty path

    @pytest.mark.asyncio
    async def test_resolve_logs_missing_skills(self, hub_setup, caplog):
        client = hub_setup[0]

        # Resolve response with missing skills
        r = client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": ["no-such-skill"]},
        )
        resolve_data = r.json()

        hub_client = KnowledgeHubClient(base_url="http://knowledgehub:9090")
        mock_response = _make_mock_httpx_response(resolve_data)
        mock_http = _make_mock_async_client(mock_response)

        with patch("aetherterm.knowledgehub.client.httpx.AsyncClient", return_value=mock_http):
            sources = await hub_client.resolve(tenant_id="t1", skill_ids=["no-such-skill"])

        assert sources == []
        assert "no-such-skill" in caplog.text

    @pytest.mark.asyncio
    async def test_resolve_empty_list(self, hub_setup):
        client = hub_setup[0]

        r = client.post(
            "/api/v1/skills/resolve",
            headers=HEADERS,
            json={"skill_ids": []},
        )
        resolve_data = r.json()

        hub_client = KnowledgeHubClient(base_url="http://knowledgehub:9090")
        mock_response = _make_mock_httpx_response(resolve_data)
        mock_http = _make_mock_async_client(mock_response)

        with patch("aetherterm.knowledgehub.client.httpx.AsyncClient", return_value=mock_http):
            sources = await hub_client.resolve(tenant_id="t1", skill_ids=[])

        assert sources == []
