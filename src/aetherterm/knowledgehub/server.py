"""ASGI application factory for KnowledgeHub service."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.knowledgehub.knowledge import KnowledgeService
from aetherterm.knowledgehub.knowledge_routes import (
    init_knowledge_routes,
    router as knowledge_router,
)
from aetherterm.knowledgehub.manager import SkillRegistryManager
from aetherterm.knowledgehub.routes import init_routes, router
from aetherterm.knowledgehub.sync.registry import SyncConnectionRegistry
from aetherterm.knowledgehub.sync_routes import (
    init_sync_routes,
    router as sync_router,
)

log = logging.getLogger("knowledgehub.server")


def create_app(
    auth: APIKeyAuthenticator | None = None,
    manager: SkillRegistryManager | None = None,
    knowledge: KnowledgeService | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create the FastAPI application for KnowledgeHub.

    Args:
        auth: API key authenticator (created if None)
        manager: SkillRegistryManager (must be provided or raises)
        knowledge: KnowledgeService (None = RAG disabled, graceful)
        cors_origins: Allowed CORS origins (default: all)
    """
    if auth is None:
        auth = APIKeyAuthenticator()
    if manager is None:
        raise ValueError("manager is required — pass a SkillRegistryManager instance")

    app = FastAPI(
        title="KnowledgeHub Service",
        description="Tenant-aware skill & document knowledge management for AetherTerm",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_routes(auth, manager)
    app.include_router(router)

    # Knowledge (RAG) routes — enabled only when KnowledgeService is provided
    if knowledge is not None:
        init_knowledge_routes(auth, knowledge)
        app.include_router(knowledge_router)
        log.info("Knowledge RAG routes enabled")

    # Sync connector routes — always enabled (connectors work independently)
    sync_registry = SyncConnectionRegistry()
    init_sync_routes(auth, sync_registry, knowledge=knowledge)
    app.include_router(sync_router)
    log.info("Sync connector routes enabled")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "knowledgehub"}

    @app.on_event("startup")
    async def startup():
        log.info("KnowledgeHub service starting")

    @app.on_event("shutdown")
    async def shutdown():
        log.info("KnowledgeHub service shutting down")

    return app
