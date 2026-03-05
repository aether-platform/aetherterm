"""REST API endpoints for tmux session/window/pane management.

Provides a full CRUD REST interface mirroring the WebSocket tmux commands.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .dependencies import TmuxRegistryDep

router = APIRouter(prefix="/api/tmux", tags=["tmux"])

log = logging.getLogger("aetherterm.tmux_routes")


# --- Request/Response Models ---


class CreateSessionRequest(BaseModel):
    name: str = ""


class CreateWindowRequest(BaseModel):
    name: str = ""
    cmd: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    role: str = ""


class RenameRequest(BaseModel):
    name: str


class SplitPaneRequest(BaseModel):
    window_id: str = ""
    pane_id: str = ""
    direction: str = "v"
    cmd: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    role: str = ""


class SendKeysRequest(BaseModel):
    data: str


class ResizePaneRequest(BaseModel):
    cols: int
    rows: int


class LayoutPresetRequest(BaseModel):
    preset: str


class ProjectSetupPaneSpec(BaseModel):
    role: str = ""
    cmd: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    cwd: Optional[str] = None
    split: str = "v"


class ProjectSetupWindowSpec(BaseModel):
    name: str = ""
    panes: list[ProjectSetupPaneSpec] = Field(default_factory=lambda: [ProjectSetupPaneSpec()])
    layout: Optional[str] = None


class ProjectSetupRequest(BaseModel):
    session_name: Optional[str] = None
    session_id: Optional[str] = None
    windows: list[ProjectSetupWindowSpec]


# --- Helpers ---


def _require_registry(registry):
    if registry is None:
        raise HTTPException(status_code=503, detail="Tmux registry not available")
    return registry


def _get_session(registry, session_id: str):
    session = registry.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


def _find_pane(registry, session_id: str, pane_id: str):
    """Find pane and its window within a session. Returns (window_id, pane)."""
    session = _get_session(registry, session_id)
    for window in session.windows.values():
        if pane_id in window.panes:
            return window.window_id, window.panes[pane_id]
    raise HTTPException(status_code=404, detail=f"Pane {pane_id} not found in session {session_id}")


# --- Session Endpoints ---


@router.post("/sessions")
async def create_session(body: CreateSessionRequest, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = reg.create_session(name=body.name)
    return session.to_dict()


@router.get("/sessions")
async def list_sessions(tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    return reg.list_sessions()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)
    return session.to_dict()


@router.delete("/sessions/{session_id}")
async def destroy_session(session_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    _get_session(reg, session_id)  # 404 if not found
    await reg.destroy_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.put("/sessions/{session_id}")
async def rename_session(session_id: str, body: RenameRequest, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)
    session.name = body.name
    return session.to_dict()


# --- Window Endpoints ---


@router.post("/sessions/{session_id}/windows")
async def create_window(
    session_id: str, body: CreateWindowRequest, tmux_registry: TmuxRegistryDep
):
    reg = _require_registry(tmux_registry)
    _get_session(reg, session_id)  # 404 if not found
    window = await reg.create_window(
        session_id, name=body.name, cmd=body.cmd, env=body.env, role=body.role
    )
    if window is None:
        raise HTTPException(status_code=500, detail="Failed to create window")
    return window.to_dict()


@router.delete("/sessions/{session_id}/windows/{window_id}")
async def close_window(session_id: str, window_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)
    if window_id not in session.windows:
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")
    ok = await reg.close_window(session_id, window_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to close window")
    return {"status": "closed", "window_id": window_id}


@router.post("/sessions/{session_id}/windows/{window_id}/select")
async def select_window(session_id: str, window_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    ok = reg.select_window(session_id, window_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session or window not found")
    return {"status": "selected", "window_id": window_id}


@router.put("/sessions/{session_id}/windows/{window_id}")
async def rename_window(
    session_id: str, window_id: str, body: RenameRequest, tmux_registry: TmuxRegistryDep
):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)
    window = session.windows.get(window_id)
    if window is None:
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")
    window.name = body.name
    return window.to_dict()


# --- Pane Endpoints ---


@router.get("/sessions/{session_id}/panes")
async def list_panes(session_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)
    panes = []
    for window in session.windows.values():
        for pane in window.panes.values():
            info = pane.to_dict()
            info["window_id"] = window.window_id
            panes.append(info)
    return panes


@router.post("/sessions/{session_id}/panes/split")
async def split_pane(session_id: str, body: SplitPaneRequest, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    session = _get_session(reg, session_id)

    # Determine window_id
    window_id = body.window_id
    if not window_id:
        if body.pane_id:
            # Find window containing the pane
            for w in session.windows.values():
                if body.pane_id in w.panes:
                    window_id = w.window_id
                    break
            if not window_id:
                raise HTTPException(status_code=404, detail=f"Pane {body.pane_id} not found")
        else:
            # Use active window
            window_id = session.active_window_id
            if not window_id:
                raise HTTPException(status_code=400, detail="No active window")

    pane = await reg.split_pane(
        session_id,
        window_id,
        target_pane_id=body.pane_id,
        direction=body.direction,
        cmd=body.cmd,
        env=body.env,
        role=body.role,
    )
    if pane is None:
        raise HTTPException(status_code=500, detail="Failed to split pane")
    return pane.to_dict()


@router.delete("/sessions/{session_id}/panes/{pane_id}")
async def close_pane(session_id: str, pane_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    window_id, _ = _find_pane(reg, session_id, pane_id)
    ok = await reg.close_pane(session_id, window_id, pane_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to close pane")
    return {"status": "closed", "pane_id": pane_id}


@router.post("/sessions/{session_id}/panes/{pane_id}/focus")
async def focus_pane(session_id: str, pane_id: str, tmux_registry: TmuxRegistryDep):
    reg = _require_registry(tmux_registry)
    window_id, _ = _find_pane(reg, session_id, pane_id)
    ok = reg.focus_pane(session_id, window_id, pane_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to focus pane")
    return {"status": "focused", "pane_id": pane_id}


@router.post("/sessions/{session_id}/panes/{pane_id}/send-keys")
async def send_keys(
    session_id: str, pane_id: str, body: SendKeysRequest, tmux_registry: TmuxRegistryDep
):
    reg = _require_registry(tmux_registry)
    window_id, _ = _find_pane(reg, session_id, pane_id)
    ok = reg.write_to_pane(session_id, window_id, pane_id, body.data.encode("utf-8"))
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to send keys (pane blocked or exited)")
    return {"status": "sent", "pane_id": pane_id}


@router.post("/sessions/{session_id}/panes/{pane_id}/resize")
async def resize_pane(
    session_id: str, pane_id: str, body: ResizePaneRequest, tmux_registry: TmuxRegistryDep
):
    reg = _require_registry(tmux_registry)
    window_id, _ = _find_pane(reg, session_id, pane_id)
    ok = reg.resize_pane_pty(session_id, window_id, pane_id, body.cols, body.rows)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to resize pane")
    return {"status": "resized", "pane_id": pane_id, "cols": body.cols, "rows": body.rows}


@router.get("/sessions/{session_id}/panes/{pane_id}/capture")
async def capture_pane(
    session_id: str,
    pane_id: str,
    tmux_registry: TmuxRegistryDep,
    lines: int = Query(default=100, ge=1, le=10000),
):
    reg = _require_registry(tmux_registry)
    _, pane = _find_pane(reg, session_id, pane_id)
    text = bytes(pane.history).decode("utf-8", errors="replace")
    all_lines = text.splitlines()
    captured = all_lines[-lines:] if len(all_lines) > lines else all_lines
    return {"pane_id": pane_id, "lines": captured}


# --- Layout Endpoints ---


@router.post("/sessions/{session_id}/windows/{window_id}/layout")
async def apply_layout(
    session_id: str, window_id: str, body: LayoutPresetRequest, tmux_registry: TmuxRegistryDep
):
    reg = _require_registry(tmux_registry)
    ok = await reg.apply_preset_layout(session_id, window_id, body.preset)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to apply layout preset")
    return {"status": "applied", "preset": body.preset}


# --- Project Setup Endpoint ---


def _build_pane_env(spec: ProjectSetupPaneSpec) -> Optional[dict[str, str]]:
    """Merge cwd into env if specified."""
    env = dict(spec.env) if spec.env else {}
    if spec.cwd:
        env["PROJECT_DIR"] = spec.cwd
    return env or None


@router.post("/project-setup")
async def project_setup(body: ProjectSetupRequest, tmux_registry: TmuxRegistryDep):
    """Create a full tmux hierarchy (session → windows → panes) from a project spec.

    Used by coding agents to scaffold a project workspace in one call.
    """
    reg = _require_registry(tmux_registry)

    # Resolve or create session
    if body.session_id:
        session = reg.get_session(body.session_id)
        if session is None:
            raise HTTPException(
                status_code=404, detail=f"Session {body.session_id} not found"
            )
    else:
        session = reg.create_session(name=body.session_name or "project")

    result_windows = []

    for win_spec in body.windows:
        pane_specs = win_spec.panes or [ProjectSetupPaneSpec()]
        first = pane_specs[0]

        # Create window (comes with first pane)
        window = await reg.create_window(
            session.session_id,
            name=win_spec.name,
            cmd=first.cmd,
            env=_build_pane_env(first),
            role=first.role,
        )
        if window is None:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create window '{win_spec.name}'",
            )

        pane_ids = list(window.panes.keys())

        # Split additional panes
        for pane_spec in pane_specs[1:]:
            pane = await reg.split_pane(
                session.session_id,
                window.window_id,
                direction=pane_spec.split,
                cmd=pane_spec.cmd,
                env=_build_pane_env(pane_spec),
                role=pane_spec.role,
            )
            if pane is None:
                log.warning(
                    f"Failed to split pane in window '{win_spec.name}', skipping"
                )
                continue
            pane_ids.append(pane.pane_id)

        # Apply layout preset if specified
        if win_spec.layout:
            await reg.apply_preset_layout(
                session.session_id, window.window_id, win_spec.layout
            )

        result_windows.append(
            {
                "window_id": window.window_id,
                "name": window.name,
                "panes": pane_ids,
            }
        )

    return {
        "session_id": session.session_id,
        "session_name": session.name,
        "windows": result_windows,
    }
