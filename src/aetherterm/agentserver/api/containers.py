import logging
import os

# TODO: python-socketio is still used here for the ASGIApp wrapper.
# Evaluate whether it can be removed after full migration to native WebSocket.
import socketio
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..core.messaging import TaskListManager
from ..core.sessions.agent_manager import AgentSessionManager
from ..core.sessions.manager import PTYSessionManager
from ..services.ai_service import create_ai_service, set_ai_service


def _create_fastapi_app(static_path):
    """Create FastAPI app with static files mounted."""
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    return app


def ai_service_instance_factory(provider, api_key, model):
    """Factory function for creating AI service instances."""
    return create_ai_service(provider=provider, api_key=api_key, model=model)


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
        cors_allowed_origins="*",  # Default to allow all origins, can be configured
    )

    # Static files path
    static_files_path = providers.Singleton(
        lambda: os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "static")
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

    # Core providers
    pty_manager = providers.Singleton(PTYSessionManager)
    task_list_manager = providers.Singleton(TaskListManager)

    agent_manager = providers.Singleton(
        AgentSessionManager,
        pty_manager=pty_manager,
    )

    # AI Service Provider
    ai_service = providers.Factory(
        ai_service_instance_factory,
        provider=config.ai_provider,
        api_key=config.ai_api_key,
        model=config.ai_model,
    )


def initialize_container(config=None):
    """Initialize and configure the dependency injection container."""
    container = ApplicationContainer()

    # Set default values first
    defaults = {
        "uri_root_path": "",
        "unsecure": False,
        "debug": False,
        "more": False,
        "ai_mode": "streaming",
        "ai_provider": "mock",  # Default to mock for testing
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
            "aetherterm.agentserver.api.routes",
            "aetherterm.agentserver.api.server",
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
        # Fallback to mock service
        from ..services.ai_service import MockAIService

        set_ai_service(MockAIService())

    return container
