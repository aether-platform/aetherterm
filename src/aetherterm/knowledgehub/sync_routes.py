"""REST API routes for sync connections (/api/v1/sync).

Matches the SDK client endpoints:
    GET    /api/v1/sync           — list connections
    POST   /api/v1/sync           — create connection
    POST   /api/v1/sync/{id}/run  — trigger sync
    POST   /api/v1/sync/{id}/pause  — pause
    POST   /api/v1/sync/{id}/resume — resume
    DELETE /api/v1/sync/{id}      — disconnect
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator, Tenant
from aetherterm.knowledgehub.knowledge import KnowledgeService
from aetherterm.knowledgehub.sync.factory import SUPPORTED_PROVIDERS, create_connector
from aetherterm.knowledgehub.sync.models import SyncConnection, SyncStatus
from aetherterm.knowledgehub.sync.registry import SyncConnectionRegistry

log = logging.getLogger("knowledgehub.sync_routes")

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_auth: APIKeyAuthenticator | None = None
_registry: SyncConnectionRegistry | None = None
_knowledge: KnowledgeService | None = None


def init_sync_routes(
    auth: APIKeyAuthenticator,
    registry: SyncConnectionRegistry,
    knowledge: KnowledgeService | None = None,
) -> None:
    """Wire up dependencies for sync routes."""
    global _auth, _registry, _knowledge
    _auth = auth
    _registry = registry
    _knowledge = knowledge


def _get_tenant(api_key: str = Depends(api_key_header_scheme)) -> Tenant:
    if not _auth or not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _auth.authenticate(api_key)


TenantDep = Annotated[Tenant, Depends(_get_tenant)]


def _ensure_registry() -> SyncConnectionRegistry:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Sync service not available")
    return _registry


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateConnectionRequest(BaseModel):
    provider: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str = ""


class ConnectionResponse(BaseModel):
    id: str
    provider: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    status: str
    schedule: str = ""
    last_sync: str = ""
    doc_count: int = 0
    created_at: str = ""
    error_message: str = ""


class SyncRunResponse(BaseModel):
    id: str
    status: str
    files_synced: int = 0
    last_sync: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn_to_response(conn: SyncConnection) -> ConnectionResponse:
    return ConnectionResponse(
        id=conn.id,
        provider=conn.provider,
        name=conn.name,
        config=conn.config,
        status=conn.status.value,
        schedule=conn.schedule,
        last_sync=conn.last_sync,
        doc_count=conn.doc_count,
        created_at=conn.created_at,
        error_message=conn.error_message,
    )


def _get_connection(registry: SyncConnectionRegistry, tenant_id: str, connection_id: str) -> SyncConnection:
    conn = registry.get(tenant_id, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    return conn


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(tenant: TenantDep):
    """List all sync connections for the tenant."""
    registry = _ensure_registry()
    connections = registry.list(tenant.tenant_id)
    return [_conn_to_response(c) for c in connections]


@router.post("", response_model=ConnectionResponse, status_code=201)
async def create_connection(req: CreateConnectionRequest, tenant: TenantDep):
    """Create a new sync connection.

    Validates the provider name and stores the connection in the registry.
    """
    registry = _ensure_registry()

    if req.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {req.provider!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}",
        )

    conn = SyncConnection(
        id=uuid.uuid4().hex[:12],
        provider=req.provider,
        name=req.name,
        config=req.config,
        schedule=req.schedule,
        tenant_id=tenant.tenant_id,
    )

    try:
        registry.create(conn)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    log.info("Created sync connection %s (%s) for tenant %s", conn.id, conn.provider, tenant.tenant_id)
    return _conn_to_response(conn)


@router.post("/{connection_id}/run", response_model=SyncRunResponse)
async def run_sync(connection_id: str, tenant: TenantDep):
    """Trigger a sync run for the given connection.

    Creates a connector, calls ``sync()``, and ingests the returned files
    into KnowledgeService.
    """
    registry = _ensure_registry()
    conn = _get_connection(registry, tenant.tenant_id, connection_id)

    if conn.status == SyncStatus.PAUSED:
        raise HTTPException(status_code=409, detail="Connection is paused — resume before syncing")

    # Mark as syncing
    registry.set_status(tenant.tenant_id, connection_id, SyncStatus.SYNCING)

    try:
        connector = create_connector(conn.provider, conn.config)
        files = await connector.sync()

        ingested = 0
        if _knowledge and files:
            for sf in files:
                if not sf.content:
                    continue
                doc_id = f"sync-{connection_id}-{uuid.uuid4().hex[:8]}"
                try:
                    await _knowledge.ingest(
                        tenant_id=tenant.tenant_id,
                        document_id=doc_id,
                        filename=sf.name,
                        content=sf.content,
                        content_type=sf.content_type,
                        tags=[f"sync:{conn.provider}", f"connection:{connection_id}"],
                    )
                    ingested += 1
                except Exception as exc:
                    log.warning("Failed to ingest %s from sync %s: %s", sf.name, connection_id, exc)

        now = datetime.now(timezone.utc).isoformat()
        conn.last_sync = now
        conn.doc_count += ingested
        conn.status = SyncStatus.IDLE
        conn.error_message = ""
        registry.update(conn)

        log.info("Sync run complete for %s: %d files ingested", connection_id, ingested)
        return SyncRunResponse(
            id=connection_id,
            status="completed",
            files_synced=ingested,
            last_sync=now,
        )

    except Exception as exc:
        log.error("Sync run failed for %s: %s", connection_id, exc)
        registry.set_status(
            tenant.tenant_id, connection_id, SyncStatus.ERROR, error_message=str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")


@router.post("/{connection_id}/pause")
async def pause_connection(connection_id: str, tenant: TenantDep):
    """Pause a sync connection (prevents future runs)."""
    registry = _ensure_registry()
    conn = _get_connection(registry, tenant.tenant_id, connection_id)

    if conn.status == SyncStatus.PAUSED:
        return {"id": connection_id, "status": "paused", "message": "Already paused"}

    registry.set_status(tenant.tenant_id, connection_id, SyncStatus.PAUSED)
    log.info("Paused sync connection %s", connection_id)
    return {"id": connection_id, "status": "paused"}


@router.post("/{connection_id}/resume")
async def resume_connection(connection_id: str, tenant: TenantDep):
    """Resume a paused sync connection."""
    registry = _ensure_registry()
    conn = _get_connection(registry, tenant.tenant_id, connection_id)

    if conn.status != SyncStatus.PAUSED:
        return {"id": connection_id, "status": conn.status.value, "message": "Not paused"}

    registry.set_status(tenant.tenant_id, connection_id, SyncStatus.IDLE)
    log.info("Resumed sync connection %s", connection_id)
    return {"id": connection_id, "status": "idle"}


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str, tenant: TenantDep):
    """Delete (disconnect) a sync connection."""
    registry = _ensure_registry()
    _get_connection(registry, tenant.tenant_id, connection_id)  # 404 check

    registry.delete(tenant.tenant_id, connection_id)
    log.info("Deleted sync connection %s for tenant %s", connection_id, tenant.tenant_id)
    return {"id": connection_id, "status": "deleted"}
