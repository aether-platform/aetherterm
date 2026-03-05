import logging
import os

import socketio
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aetherterm.agentserver.adapters.outbound.memory_terminal_repo import InMemoryTerminalRepository
from aetherterm.agentserver.adapters.outbound.socketio_broadcaster import SocketIOBroadcaster
from aetherterm.agentserver.ai_services import create_ai_service, set_ai_service
from aetherterm.agentserver.application.use_cases.blocker_use_cases import BlockerUseCases
from aetherterm.agentserver.application.use_cases.terminal_use_cases import TerminalUseCases
from aetherterm.agentserver.domain.services.session_blocker import SessionBlockerService
from aetherterm.agentserver.domain.services.threat_detection import ThreatDetectionService


def _create_fastapi_app(static_path):
    """Create FastAPI app with static files mounted."""
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    return app


class ApplicationContainer(containers.DeclarativeContainer):
    """Root container for the application, focused on Terminal dependency injection."""

    config = providers.Configuration()

    # Logging configuration
    logging_level = providers.Callable(
        lambda debug, more: (
            logging.DEBUG if more else (logging.INFO if debug else logging.WARNING)
        ),
        debug=config.debug,
        more=config.more,
    )

    # Socket.IO server provider
    sio = providers.Singleton(
        socketio.AsyncServer,
        async_mode="asgi",
        cors_allowed_origins="*",
    )

    # Static files path
    static_files_path = providers.Singleton(
        lambda: os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    )

    # FastAPI application provider for static files and HTTP routes
    fastapi_app = providers.Singleton(
        lambda static_path: _create_fastapi_app(static_path),
        static_path=static_files_path,
    )

    # Combined ASGI application (Socket.IO + FastAPI)
    app = providers.Singleton(
        socketio.ASGIApp,
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path=providers.Callable(
            lambda uri_root_path: f"{uri_root_path}/socket.io" if uri_root_path else "/socket.io",
            uri_root_path=config.uri_root_path,
        ),
    )

    # AI Service Provider
    ai_service = providers.Factory(
        create_ai_service,
        provider=config.ai_provider,
        api_key=config.ai_api_key,
        model=config.ai_model,
    )

    # --- Clean Architecture layers ---

    # Domain Services
    threat_detector = providers.Singleton(ThreatDetectionService)
    session_blocker = providers.Singleton(SessionBlockerService)

    # Adapters (outbound)
    broadcaster = providers.Singleton(SocketIOBroadcaster, sio=sio)
    terminal_repo = providers.Singleton(InMemoryTerminalRepository)

    # Use Cases
    terminal_use_cases = providers.Singleton(
        TerminalUseCases,
        terminal_repo=terminal_repo,
        broadcaster=broadcaster,
        threat_detector=threat_detector,
        session_blocker=session_blocker,
    )

    blocker_use_cases = providers.Singleton(
        BlockerUseCases,
        session_blocker=session_blocker,
        broadcaster=broadcaster,
        terminal_repo=terminal_repo,
    )


def configure_container(config=None):
    """Configure the dependency injection container."""
    container = ApplicationContainer()

    # Set default values first
    defaults = {
        "uri_root_path": "",
        "unsecure": False,
        "debug": False,
        "more": False,
        "ai_mode": "streaming",
        "ai_provider": "mock",
        "ai_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "ai_model": "claude-3-5-sonnet-20241022",
    }

    # Merge defaults with provided config
    final_config = defaults.copy()
    if config:
        final_config.update(config)

    container.config.from_dict(final_config)

    container.wire(
        modules=[
            "aetherterm.agentserver.routes",
            "aetherterm.agentserver.server",
            "aetherterm.agentserver.socket_handlers.terminal_handlers",
            "aetherterm.agentserver.socket_handlers.blocker_handlers",
            "aetherterm.agentserver.socket_handlers.ai_handlers",
        ]
    )

    # Initialize AI service
    try:
        ai_service_instance = container.ai_service()
        set_ai_service(ai_service_instance)
        logging.getLogger("aetherterm.agentserver.containers").info(
            f"AI service initialized with provider: {final_config.get('ai_provider', 'unknown')}"
        )
    except Exception as e:
        logging.getLogger("aetherterm.agentserver.containers").error(
            f"Failed to initialize AI service: {e}"
        )
        from aetherterm.agentserver.ai_services import MockAIService
        set_ai_service(MockAIService())
    return container
