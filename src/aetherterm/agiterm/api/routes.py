"""REST API routes for WorkWithAGI SDK."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator, Tenant, api_key_header
from aetherterm.agiterm.sessions.manager import SDKSessionManager

log = logging.getLogger("agiterm.api")

router = APIRouter(prefix="/api/v1", tags=["sdk"])

_auth: APIKeyAuthenticator | None = None
_sessions: SDKSessionManager | None = None


def init_routes(auth: APIKeyAuthenticator, sessions: SDKSessionManager) -> None:
    global _auth, _sessions
    _auth = auth
    _sessions = sessions


def get_tenant(api_key: str = Depends(api_key_header)) -> Tenant:
    if not _auth or not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _auth.authenticate(api_key)


# --- Models ---


class CreateSessionRequest(BaseModel):
    user_id: str
    tool: str = "bash"
    cols: int = 80
    rows: int = 24
    label: str = ""
    prompt: str = ""
    skill_ids: list[str] = []
    runtime_handler: str = ""


class SessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    tool: str
    label: str
    ws_url: str
    backend_type: str = "direct"


class AddPaneRequest(BaseModel):
    tool: str = "bash"
    role: str = ""
    cols: int = 80
    rows: int = 24


class PaneResponse(BaseModel):
    pane_id: str
    tool: str
    role: str
    title: str


# --- Endpoints ---


@router.get("/health")
async def health():
    return {"status": "ok", "service": "agiterm"}


@router.get("/tools")
async def list_tools():
    """List available AI CLI tools and their status."""
    return _sessions.available_tools()


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    tenant: Tenant = Depends(get_tenant),
):
    """Create a new terminal session with the specified tool."""
    existing = _sessions.list_sessions(tenant.tenant_id)
    if len(existing) >= tenant.max_sessions:
        raise HTTPException(
            status_code=429,
            detail=f"Max sessions ({tenant.max_sessions}) reached",
        )

    # Resolve skills via KnowledgeHub if skill_ids provided
    skills = None
    if req.skill_ids:
        hub_url = os.environ.get("KNOWLEDGEHUB_URL", "")
        if hub_url:
            from aetherterm.knowledgehub.client import KnowledgeHubClient

            client = KnowledgeHubClient(base_url=hub_url)
            try:
                skills = await client.resolve(tenant.tenant_id, req.skill_ids)
            except Exception as e:
                log.warning("KnowledgeHub resolve failed: %s", e)
        else:
            log.warning("skill_ids requested but KNOWLEDGEHUB_URL not set")

    try:
        session = await _sessions.create_session(
            tenant_id=tenant.tenant_id,
            user_id=req.user_id,
            tool=req.tool,
            cols=req.cols,
            rows=req.rows,
            label=req.label,
            prompt=req.prompt,
            skills=skills,
            runtime_handler=req.runtime_handler,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SessionResponse(
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        tool=session.tool,
        label=session.label,
        ws_url=f"/ws/sdk/{session.session_id}",
        backend_type=session.backend_type,
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(tenant: Tenant = Depends(get_tenant)):
    sessions = _sessions.list_sessions(tenant.tenant_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            tenant_id=s.tenant_id,
            user_id=s.user_id,
            tool=s.tool,
            label=s.label,
            ws_url=f"/ws/sdk/{s.session_id}",
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def destroy_session(
    session_id: str,
    tenant: Tenant = Depends(get_tenant),
):
    ok = await _sessions.destroy_session(session_id, tenant.tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "destroyed", "session_id": session_id}


@router.post("/sessions/{session_id}/resize")
async def resize_session(
    session_id: str,
    cols: int,
    rows: int,
    tenant: Tenant = Depends(get_tenant),
):
    session = _sessions.get_session(session_id, tenant.tenant_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.pty_session.resize(cols, rows)
    return {"status": "resized", "cols": cols, "rows": rows}


# --- Pane management (workspace multi-pane) ---


@router.post("/sessions/{session_id}/panes", response_model=PaneResponse)
async def add_pane(
    session_id: str,
    req: AddPaneRequest,
    tenant: Tenant = Depends(get_tenant),
):
    """Add a new pane to a session workspace."""
    try:
        pane = await _sessions.add_pane(
            session_id=session_id,
            tenant_id=tenant.tenant_id,
            tool=req.tool,
            role=req.role,
            cols=req.cols,
            rows=req.rows,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PaneResponse(
        pane_id=pane.pane_id,
        tool=pane.tool,
        role=pane.role,
        title=pane.title,
    )


@router.delete("/sessions/{session_id}/panes/{pane_id}")
async def remove_pane(
    session_id: str,
    pane_id: str,
    tenant: Tenant = Depends(get_tenant),
):
    """Remove a pane from a session workspace."""
    ok = await _sessions.remove_pane(session_id, tenant.tenant_id, pane_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pane not found")
    return {"status": "removed", "pane_id": pane_id}


@router.get("/sessions/{session_id}/layout")
async def get_layout(
    session_id: str,
    tenant: Tenant = Depends(get_tenant),
):
    """Get the current layout tree for a session workspace."""
    layout = _sessions.get_layout(session_id, tenant.tenant_id)
    if layout is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "layout": layout}
