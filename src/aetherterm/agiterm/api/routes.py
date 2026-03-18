"""REST API routes for WorkWithAGI SDK."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator, Tenant, api_key_header
from aetherterm.agiterm.sessions.manager import SDKSessionManager

log = logging.getLogger("agiterm.api")

router = APIRouter(prefix="/api/v1", tags=["sdk"])

# Singletons — injected at app startup
_auth: APIKeyAuthenticator | None = None
_sessions: SDKSessionManager | None = None


def init_routes(auth: APIKeyAuthenticator, sessions: SDKSessionManager) -> None:
    """Inject dependencies into routes."""
    global _auth, _sessions
    _auth = auth
    _sessions = sessions


def get_tenant(api_key: str = Depends(api_key_header)) -> Tenant:
    """Dependency: authenticate and return tenant."""
    if not _auth or not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _auth.authenticate(api_key)


# --- Models ---


class CreateSessionRequest(BaseModel):
    user_id: str
    shell: str = "/bin/bash"
    cols: int = 80
    rows: int = 24
    label: str = ""


class SessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    label: str
    ws_url: str


# --- Endpoints ---


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": "agiterm"}


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    tenant: Tenant = Depends(get_tenant),
):
    """Create a new terminal session."""
    existing = _sessions.list_sessions(tenant.tenant_id)
    if len(existing) >= tenant.max_sessions:
        raise HTTPException(
            status_code=429,
            detail=f"Max sessions ({tenant.max_sessions}) reached",
        )

    session = await _sessions.create_session(
        tenant_id=tenant.tenant_id,
        user_id=req.user_id,
        shell=req.shell,
        cols=req.cols,
        rows=req.rows,
        label=req.label,
    )

    return SessionResponse(
        session_id=session.session_id,
        tenant_id=session.tenant_id,
        user_id=session.user_id,
        label=session.label,
        ws_url=f"/ws/sdk/{session.session_id}",
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(tenant: Tenant = Depends(get_tenant)):
    """List all sessions for the authenticated tenant."""
    sessions = _sessions.list_sessions(tenant.tenant_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            tenant_id=s.tenant_id,
            user_id=s.user_id,
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
    """Destroy a terminal session."""
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
    """Resize a session's PTY."""
    session = _sessions.get_session(session_id, tenant.tenant_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.pty_session.resize(cols, rows)
    return {"status": "resized", "cols": cols, "rows": rows}
