import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..core.activity import get_event_hub
from ..core.nats_bridge import NATSControlBridge
from ..core.messaging import MessageRouter
from ..core.sessions.tmux.session_registry import TmuxSessionRegistry
from ..core.sessions.tmux.wm_socket import WmSocketServer
from ..core.sessions.tmux.ws_handler import TmuxWebSocketHandler
from .containers import initialize_container
from .handlers import ControlCommandHandler, handle_agent_websocket
from .routes import router as api_router
from .tmux_routes import router as tmux_api_router

log = logging.getLogger("aetherterm.server")

_SHIM_DIR = Path(f"/tmp/aetherterm-shim-{os.getuid()}")


def _setup_tmux_shim_path() -> None:
    """Create a shim directory with `tmux` symlinked to `aetherterm-tmux-shim`.

    Prepends the directory to PATH so child processes (Claude --teammate-mode tmux)
    use our shim instead of the real tmux binary.
    """
    _SHIM_DIR.mkdir(parents=True, exist_ok=True)
    shim_bin = shutil.which("aetherterm-tmux-shim")
    if not shim_bin:
        log.warning("aetherterm-tmux-shim not found on PATH; tmux shim disabled")
        return

    tmux_link = _SHIM_DIR / "tmux"
    if tmux_link.exists() or tmux_link.is_symlink():
        tmux_link.unlink()
    tmux_link.symlink_to(shim_bin)

    # Prepend shim dir to PATH for this process and all children
    current_path = os.environ.get("PATH", "")
    shim_str = str(_SHIM_DIR)
    if shim_str not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{shim_str}{os.pathsep}{current_path}"
    log.info("tmux-shim installed: %s -> %s", tmux_link, shim_bin)


def create_asgi_app(config: Dict[str, Any] = None) -> Any:
    """ASGI application factory for creating the combined Socket.IO and FastAPI app."""
    container = initialize_container(config)

    # Get the FastAPI app and Socket.IO server from the container
    app = container.fastapi_app()
    sio = container.sio()

    # Core managers from container
    psm = container.pty_manager()
    asm = container.agent_manager()

    tmux_registry = TmuxSessionRegistry()

    # NATSControlBridge: NATS pub/sub to ControlServer
    control_bridge = NATSControlBridge()

    # MessageRouter
    message_router = MessageRouter()
    task_list_manager = container.task_list_manager()

    tmux_registry.message_router = message_router
    tmux_ws = TmuxWebSocketHandler(tmux_registry, message_router=message_router)

    # ControlCommand Handler
    control_handler = ControlCommandHandler(tmux_registry)

    # Store on app.state for access from routes and other components
    app.state.control_bridge = control_bridge
    app.state.control_handler = control_handler
    app.state.message_router = message_router
    app.state.task_list_manager = task_list_manager
    app.state.tmux_registry = tmux_registry
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(tmux_api_router)

    # --- Lifecycle ---

    @app.on_event("startup")
    async def startup_control_bridge():
        # Forward control commands to ControlCommandHandler
        control_bridge.on_control_command(control_handler.handle_command)

        # Forward PTY output to NATSControlBridge
        async def _forward_pty_output(session_id: str, pane_id: str, data: bytes) -> None:
            await control_bridge.forward_log(session_id, pane_id, data)

        tmux_registry.on_pane_output(_forward_pty_output)

        await control_bridge.start()
        app.state._bg_tasks = set()
        t1 = asyncio.create_task(_session_report_loop(control_bridge, tmux_registry))
        app.state._bg_tasks.add(t1)
        t1.add_done_callback(app.state._bg_tasks.discard)

        # Start WM socket server for tmux-shim CLI access
        wm_socket = WmSocketServer(tmux_registry)
        app.state.wm_socket = wm_socket
        t2 = asyncio.create_task(wm_socket.start())
        app.state._bg_tasks.add(t2)
        t2.add_done_callback(app.state._bg_tasks.discard)

        # Create shim directory so child processes find `tmux` → tmux-shim
        _setup_tmux_shim_path()

    @app.on_event("shutdown")
    async def shutdown_all():
        wm_socket = getattr(app.state, "wm_socket", None)
        if wm_socket:
            await wm_socket.stop()
        await tmux_registry.cleanup_all()
        await control_bridge.stop()
        log.info("Shutdown complete")

    # --- WebSockets ---

    @app.websocket("/ws/pty/{session_id}")
    async def pty_ws_wrapper(websocket: WebSocket, session_id: str):
        # Local wrapper to keep it in server.py or move to handlers?
        # Keeping minimal wrapper here for now.
        await _handle_pty_websocket(websocket, session_id, psm)

    @app.websocket("/ws/agent/{agent_id}")
    async def agent_ws_wrapper(websocket: WebSocket, agent_id: str):
        await handle_agent_websocket(
            websocket, agent_id, message_router, asm, tmux_registry
        )

    @app.websocket("/ws/tmux/{session_id}")
    async def tmux_ws_wrapper(websocket: WebSocket, session_id: str):
        await tmux_ws.handle(websocket, session_id)

    @app.websocket("/ws/events")
    async def events_ws(websocket: WebSocket):
        """EventHub: push state-change events to connected browsers."""
        hub = get_event_hub()
        await hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            hub.disconnect(websocket)

    # --- Proxy & Static ---

    OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "http://open-webui:8080")

    @app.api_route("/api/chat-ui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_open_webui(path: str, request: Request):
        async with httpx.AsyncClient() as client:
            url = f"{OPEN_WEBUI_URL}/{path}"
            headers = dict(request.headers)
            headers.pop("host", None)
            res = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=await request.body(),
                params=request.query_params,
            )
            return Response(
                content=res.content, status_code=res.status_code, headers=dict(res.headers)
            )

    # SPA: env override > frontend/dist > installed web/static
    dist_path = os.environ.get("AETHERTERM_STATIC_DIR", "")
    if not dist_path or not os.path.isdir(dist_path):
        dist_path = os.path.join(os.getcwd(), "frontend/dist")
    if not os.path.isdir(dist_path):
        dist_path = os.path.join(os.path.dirname(__file__), "..", "web", "static")
    if os.path.isdir(dist_path):
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="spa")

    return container.app()


async def _session_report_loop(bridge: NATSControlBridge, registry: TmuxSessionRegistry) -> None:
    while True:
        try:
            await asyncio.sleep(10)
            if not bridge.is_connected:
                continue
            sessions = []
            for session in registry.sessions.values():
                pane_ids = []
                windows = []
                for window in session.windows.values():
                    pane_ids.extend(window.panes.keys())
                    pane_details = []
                    for pane in window.panes.values():
                        pane_details.append({
                            "pane_id": pane.pane_id,
                            "status": pane.status.value,
                            "role": pane.role,
                            "title": pane.title,
                            "cols": pane.cols,
                            "rows": pane.rows,
                            "exit_code": pane.exit_code,
                            "created_at": pane.created_at,
                        })
                    windows.append({
                        "window_id": window.window_id,
                        "name": window.name,
                        "active_pane_id": window.active_pane_id,
                        "panes": pane_details,
                    })
                sessions.append(
                    {
                        "session_id": session.session_id,
                        "name": session.name,
                        "pane_ids": pane_ids,
                        "window_count": len(session.windows),
                        "windows": windows,
                        "created_at": session.created_at,
                    }
                )
            if sessions:
                await bridge.send_session_report(sessions)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Session report loop error")
            await asyncio.sleep(10)


async def _handle_pty_websocket(websocket: WebSocket, session_id: str, psm: Any):
    await websocket.accept()
    session = psm.create_session(session_id)
    queue = asyncio.Queue()
    session.clients.add(queue)

    if session.history:
        await websocket.send_bytes(session.history)

    async def read_from_socket():
        try:
            while True:
                data = await websocket.receive()
                if "text" in data:
                    try:
                        msg = json.loads(data["text"])
                        if msg.get("type") == "resize":
                            session.resize(msg["cols"], msg["rows"])
                        elif msg.get("type") == "input":
                            session.write(msg["data"].encode("utf-8"))
                    except (json.JSONDecodeError, KeyError):
                        session.write(data["text"].encode("utf-8"))
                elif "bytes" in data:
                    session.write(data["bytes"])
        except Exception:
            pass
        finally:
            session.clients.remove(queue)

    async def write_to_socket():
        try:
            while True:
                data = await queue.get()
                if data is None:
                    break
                await websocket.send_bytes(data)
        except Exception:
            pass

    await asyncio.gather(read_from_socket(), write_to_socket())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_asgi_app(), host="0.0.0.0", port=57575)
