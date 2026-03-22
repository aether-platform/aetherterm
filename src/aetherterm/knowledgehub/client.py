"""HTTP client for KnowledgeHub — used by agiterm and agentserver."""

from __future__ import annotations

import logging

import httpx

from aetherterm.agiterm.sessions.manager import SkillSource

log = logging.getLogger("knowledgehub.client")


class KnowledgeHubClient:
    """Async HTTP client for the KnowledgeHub service.

    Provides access to both skill resolution and knowledge search.
    """

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    # ---- Skills ----

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(f"{self._base_url}/health")
            r.raise_for_status()
            return r.json()

    async def list_skills(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._base_url}/api/v1/skills",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def resolve(self, tenant_id: str, skill_ids: list[str]) -> list[SkillSource]:
        """Resolve skill_ids and return SkillSource objects ready for inject_skills()."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base_url}/api/v1/skills/resolve",
                headers=self._headers(),
                json={"skill_ids": skill_ids},
            )
            r.raise_for_status()
            data = r.json()

        sources: list[SkillSource] = []
        for item in data.get("resolved", []):
            sources.append(
                SkillSource(
                    provider=item["provider"],
                    skill_dir=item["skill_dir"],
                    context=item.get("context", ""),
                    env=item.get("env", {}),
                )
            )

        missing = data.get("missing", [])
        if missing:
            log.warning("Skills not found: %s", missing)

        return sources

    # ---- Knowledge (RAG) ----

    async def search_knowledge(
        self, query: str, limit: int = 10, document_id: str = ""
    ) -> list[dict]:
        """Semantic search across the tenant's knowledge base."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base_url}/api/v1/knowledge/search",
                headers=self._headers(),
                json={"query": query, "limit": limit, "document_id": document_id},
            )
            r.raise_for_status()
            return r.json().get("results", [])

    async def build_context(self, query: str, limit: int = 5) -> str:
        """Search knowledge and return formatted context for CLAUDE.md injection."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base_url}/api/v1/knowledge/context",
                headers=self._headers(),
                json={"query": query, "limit": limit},
            )
            r.raise_for_status()
            return r.json().get("context", "")
