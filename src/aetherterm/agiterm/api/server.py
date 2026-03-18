"""ASGI application factory for WorkWithAGI SDK server."""

import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.agiterm.sessions.manager import SDKSessionManager
from aetherterm.agiterm.api.routes import router, init_routes
from aetherterm.agiterm.api.ws_handler import handle_sdk_websocket

log = logging.getLogger("agiterm.server")


def create_app(
    auth: APIKeyAuthenticator | None = None,
    sessions: SDKSessionManager | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create the FastAPI application for WorkWithAGI SDK.

    Args:
        auth: API key authenticator (created if None)
        sessions: Session manager (created if None)
        cors_origins: Allowed CORS origins (default: all)
    """
    if auth is None:
        auth = APIKeyAuthenticator()
    if sessions is None:
        sessions = SDKSessionManager()

    app = FastAPI(
        title="WorkWithAGI SDK Server",
        description="Terminal & Code Search API for WorkWithAGI SDK",
        version="0.1.0",
    )

    # CORS — SDK is embedded in third-party apps
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inject dependencies into routes
    init_routes(auth, sessions)
    app.include_router(router)

    # WebSocket endpoint for terminal sessions
    @app.websocket("/ws/sdk/{session_id}")
    async def ws_sdk(websocket: WebSocket, session_id: str):
        await handle_sdk_websocket(websocket, session_id, auth, sessions)

    @app.on_event("startup")
    async def startup():
        log.info("WorkWithAGI SDK server starting")

    @app.on_event("shutdown")
    async def shutdown():
        log.info("WorkWithAGI SDK server shutting down")
        # Clean up all sessions
        for session in list(sessions._sessions.values()):
            await sessions.destroy_session(
                session.session_id, session.tenant_id
            )

    return app
