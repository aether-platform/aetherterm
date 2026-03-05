import asyncio
import json
import logging
import os
from typing import Any, Dict

import httpx
from fastapi import Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..core.control_bridge import ControlBridge
from ..core.messaging import MessageRouter
from ..core.sessions.tmux.session_registry import TmuxSessionRegistry
from ..core.sessions.tmux.ws_handler import TmuxWebSocketHandler
from .containers import initialize_container
from .routes import router as api_router
from .tmux_routes import router as tmux_api_router

log = logging.getLogger("aetherterm.server")


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

    # ControlBridge: direct DEALER/SUB to ControlServer
    control_bridge = ControlBridge()

    # MessageRouter (no longer depends on ZMQ Broker)
    message_router = MessageRouter()
    task_list_manager = container.task_list_manager()

    tmux_registry.message_router = message_router
    tmux_ws = TmuxWebSocketHandler(tmux_registry, message_router=message_router)

    # ControlCommand Handler
    from .handlers import ControlCommandHandler, handle_agent_websocket

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

        # Forward PTY output to ControlBridge
        async def _forward_pty_output(session_id: str, pane_id: str, data: bytes) -> None:
            await control_bridge.forward_log(session_id, pane_id, data)

        tmux_registry.on_pane_output(_forward_pty_output)

        await control_bridge.start()
        asyncio.create_task(_session_report_loop(control_bridge, tmux_registry))

    @app.on_event("shutdown")
    async def shutdown_all():
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

    # SPA: prefer development frontend/dist, fallback to installed web/static
    dist_path = os.path.join(os.getcwd(), "frontend/dist")
    if not os.path.isdir(dist_path):
        dist_path = os.path.join(os.path.dirname(__file__), "..", "web", "static")
    if os.path.isdir(dist_path):
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="spa")

    return container.app()


async def _session_report_loop(bridge: ControlBridge, registry: TmuxSessionRegistry) -> None:
    while True:
        try:
            await asyncio.sleep(10)
            if not bridge.is_connected:
                continue
            sessions = []
            for session in registry.sessions.values():
                pane_ids = []
                for window in session.windows.values():
                    pane_ids.extend(window.panes.keys())
                sessions.append(
                    {
                        "session_id": session.session_id,
                        "name": session.name,
                        "pane_ids": pane_ids,
                        "window_count": len(session.windows),
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
