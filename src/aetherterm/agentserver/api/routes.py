# This file is part of aetherterm
#
# aetherterm Copyright(C) 2015-2017 Florian Mounier
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
from mimetypes import guess_type

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from ..core.messaging import TaskListManager
from .dependencies import ControlBridgeDep, ControlHandlerDep, TmuxRegistryDep

# Initialize FastAPI router
router = APIRouter()

log = logging.getLogger("aetherterm.routes")

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "..", "web", "templates")
)

# Mount static files directory
static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")
if os.path.exists(static_dir) and os.listdir(static_dir):
    router.mount("/static", StaticFiles(directory=static_dir), name="static")


@router.get("/health")
async def health(
    tmux_registry: TmuxRegistryDep = None,
    control_bridge: ControlBridgeDep = None,
):
    """Health check endpoint for Docker/Kubernetes."""
    result: dict = {"status": "healthy"}
    if tmux_registry:
        result["tmux_sessions"] = len(tmux_registry.list_sessions())
    if control_bridge:
        result["control_bridge"] = {"connected": control_bridge.is_connected}
    return JSONResponse(result)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main index route that serves the terminal interface."""
    # Dynamically find the hashed asset filenames
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static", "assets")
    js_bundle = ""
    css_bundle = ""
    # Get root path from configuration
    container = request.app.state.container
    config = container.config()
    root_path = config.get("uri_root_path", "")

    for filename in os.listdir(assets_dir):
        if filename.startswith("index.") and filename.endswith(".js"):
            js_bundle = f"{root_path}/static/assets/{filename}"
        elif filename.startswith("index.") and filename.endswith(".css"):
            css_bundle = f"{root_path}/static/assets/{filename}"

    if not js_bundle or not css_bundle:
        raise HTTPException(status_code=500, detail="Could not find hashed JS or CSS files")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "js_bundle": js_bundle,
            "css_bundle": css_bundle,
            "favicon_path": f"{root_path}/static/favicon.ico",
            "uri_root_path": root_path,
        },
    )


@router.get("/theme/{theme}/style.css")
async def theme_style(theme: str):
    """Serve theme CSS files."""
    try:
        import sass
    except ImportError:
        log.error("You must install libsass to use sass (pip install libsass)")
        raise HTTPException(status_code=500, detail="Sass compiler not available")

    # Get theme directory
    themes_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "themes")
    builtin_themes_dir = os.path.join(os.path.dirname(__file__), "..", "web", "themes")

    base_dir = None
    if theme.startswith("built-in-"):
        theme_name = theme[9:]  # Remove 'built-in-' prefix
        base_dir = os.path.join(builtin_themes_dir, theme_name)
    else:
        base_dir = os.path.join(themes_dir, theme)

    if not os.path.exists(base_dir):
        raise HTTPException(status_code=404, detail="Theme not found")

    # Look for style file
    style = None
    for ext in ["css", "scss", "sass"]:
        probable_style = os.path.join(base_dir, f"style.{ext}")
        if os.path.exists(probable_style):
            style = probable_style
            break

    if not style:
        raise HTTPException(status_code=404, detail="Style file not found")

    # Compile sass if needed
    sass_path = os.path.join(os.path.dirname(__file__), "..", "web", "sass")

    try:
        css = sass.compile(filename=style, include_paths=[base_dir, sass_path])
        return Response(content=css, media_type="text/css")
    except Exception as e:
        log.error(f"Unable to compile style: {e}")
        raise HTTPException(status_code=500, detail="Style compilation failed")


@router.get("/theme/{theme}/{filename:path}")
async def theme_static(theme: str, filename: str):
    """Serve static theme files."""
    if ".." in filename:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get theme directory
    themes_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "themes")
    builtin_themes_dir = os.path.join(os.path.dirname(__file__), "..", "web", "themes")

    base_dir = None
    if theme.startswith("built-in-"):
        theme_name = theme[9:]  # Remove 'built-in-' prefix
        base_dir = os.path.join(builtin_themes_dir, theme_name)
    else:
        base_dir = os.path.join(themes_dir, theme)

    file_path = os.path.normpath(os.path.join(base_dir, filename))

    # Security check
    if not file_path.startswith(base_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type = guess_type(file_path)[0]
    if content_type is None:
        # Fallback content types
        ext = filename.split(".")[-1].lower()
        content_type = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "woff": "application/font-woff",
            "ttf": "application/x-font-ttf",
        }.get(ext, "text/plain")

    return FileResponse(file_path, media_type=content_type)

    # This legacy endpoint needs proper session/user retrieval logic if still used.
    # For now, keeping it as a stub or removing it if replaced by /pty and /tmux.
    # The original server.py didn't have this exact logic in the same way.
    # Removing for now to fix 'undefined name' errors as it's likely legacy.


# --- PTY Session Management API ---


@router.get("/pty")
async def list_pty_sessions(request: Request):
    psm = request.app.state.container.pty_manager()
    return [
        {
            "id": s.id,
            "pid": s.pid,
            "active_clients": len(s.clients),
            "history_size": len(s.history),
        }
        for s in psm.sessions.values()
    ]


@router.delete("/pty/{session_id}")
async def delete_pty_session(session_id: str, request: Request):
    psm = request.app.state.container.pty_manager()
    psm.remove_session(session_id)
    return {"status": "deleted"}


# --- Task List REST API ---


@router.get("/tasks/{session_id}")
async def list_tasks(session_id: str, request: Request):
    tlm: TaskListManager = request.app.state.task_list_manager
    return [t.to_dict() for t in tlm.list_tasks()]


@router.post("/tasks/{session_id}")
async def create_task(session_id: str, request: Request):
    tlm: TaskListManager = request.app.state.task_list_manager
    body = await request.json()
    task = tlm.create_task(
        subject=body.get("subject", ""),
        description=body.get("description", ""),
        active_form=body.get("active_form", ""),
    )
    return task.to_dict()


@router.put("/tasks/{session_id}/{task_id}")
async def update_task(session_id: str, task_id: str, request: Request):
    tlm: TaskListManager = request.app.state.task_list_manager
    body = await request.json()
    task = tlm.update_task(task_id, **body)
    if task is None:
        return Response(status_code=404, content='{"error":"not found"}')
    return task.to_dict()


@router.delete("/tasks/{session_id}/{task_id}")
async def delete_task(session_id: str, task_id: str, request: Request):
    tlm: TaskListManager = request.app.state.task_list_manager
    if tlm.delete_task(task_id):
        return {"status": "deleted"}
    return Response(status_code=404, content='{"error":"not found"}')


# --- tmux Session Management API ---


@router.get("/tmux/sessions")
async def list_tmux_sessions(tmux_registry: TmuxRegistryDep):
    return tmux_registry.list_sessions()


@router.delete("/tmux/sessions/{session_id}")
async def delete_tmux_session(session_id: str, tmux_registry: TmuxRegistryDep):
    await tmux_registry.destroy_session(session_id)
    return {"status": "deleted"}


# --- Control API ---


@router.get("/api/control/status")
async def control_status(
    control_bridge: ControlBridgeDep = None,
    tmux_registry: TmuxRegistryDep = None,
):
    """Get NATSControlBridge connection status and session counts."""
    result: dict = {"connected": False, "sessions": 0, "transport": "nats"}
    if control_bridge:
        result["connected"] = control_bridge.is_connected
        result["agent_server_id"] = getattr(control_bridge, "agent_server_id", "")
    if tmux_registry:
        result["sessions"] = len(tmux_registry.list_sessions())
    return JSONResponse(result)


@router.post("/api/control/emergency-stop")
async def emergency_stop(request: Request, control_handler: ControlHandlerDep = None):
    """Trigger emergency stop — destroys all sessions locally and notifies ControlServer."""
    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()

    if control_handler is None:
        raise HTTPException(status_code=503, detail="Control handler not available")

    await control_handler.handle_command("emergency_stop", body)
    return JSONResponse({"status": "emergency_stop_triggered"})


@router.post("/api/control/block-input")
async def block_input(request: Request, control_handler: ControlHandlerDep = None):
    """Block input for a session or specific pane."""
    body = await request.json()
    if control_handler is None:
        raise HTTPException(status_code=503, detail="Control handler not available")

    session_id = body.get("session_id", "")
    pane_id = body.get("pane_id", "")
    if not session_id and not pane_id:
        raise HTTPException(status_code=400, detail="session_id or pane_id required")

    await control_handler.handle_command("block_input", body)
    return JSONResponse({"status": "input_blocked", "session_id": session_id, "pane_id": pane_id})


@router.post("/api/control/unblock-input")
async def unblock_input(request: Request, control_handler: ControlHandlerDep = None):
    """Unblock input for a session or specific pane."""
    body = await request.json()
    if control_handler is None:
        raise HTTPException(status_code=503, detail="Control handler not available")

    session_id = body.get("session_id", "")
    pane_id = body.get("pane_id", "")
    if not session_id and not pane_id:
        raise HTTPException(status_code=400, detail="session_id or pane_id required")

    await control_handler.handle_command("unblock_input", body)
    return JSONResponse(
        {"status": "input_unblocked", "session_id": session_id, "pane_id": pane_id}
    )


@router.post("/api/control/kill-session")
async def kill_session(request: Request, control_handler: ControlHandlerDep = None):
    """Kill (destroy) a specific tmux session."""
    body = await request.json()
    if control_handler is None:
        raise HTTPException(status_code=503, detail="Control handler not available")

    session_id = body.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    await control_handler.handle_command("kill_session", body)
    return JSONResponse({"status": "session_killed", "session_id": session_id})


@router.get("/themes/list.json")
async def themes_list():
    """Get the list of available themes."""
    themes_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "themes")
    builtin_themes_dir = os.path.join(os.path.dirname(__file__), "..", "web", "themes")

    themes = []
    if os.path.exists(themes_dir):
        themes = [
            theme
            for theme in os.listdir(themes_dir)
            if os.path.isdir(os.path.join(themes_dir, theme)) and not theme.startswith(".")
        ]

    builtin_themes = []
    if os.path.exists(builtin_themes_dir):
        builtin_themes = [
            f"built-in-{theme}"
            for theme in os.listdir(builtin_themes_dir)
            if os.path.isdir(os.path.join(builtin_themes_dir, theme)) and not theme.startswith(".")
        ]

    return JSONResponse(
        {
            "themes": sorted(themes),
            "builtin_themes": sorted(builtin_themes),
            "dir": themes_dir,
        }
    )


@router.get("/local.js")
async def local_js():
    """Serve local JavaScript files."""
    local_js_dir = os.path.join(os.path.expanduser("~"), ".config", "aetherterm", "local.js")

    js_content = ""
    if os.path.exists(local_js_dir):
        for filename in os.listdir(local_js_dir):
            if not filename.endswith(".js"):
                continue
            file_path = os.path.join(local_js_dir, filename)
            try:
                with open(file_path, encoding="utf-8") as f:
                    js_content += f.read() + ";\n"
            except Exception as e:
                log.warning(f"Could not read {file_path}: {e}")

    return Response(content=js_content, media_type="application/javascript")
