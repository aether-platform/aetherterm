"""
Application Factory Module - Web Interface Layer

Handles ASGI application creation and configuration.
Implements Clean Architecture principles with dependency injection.
"""

import logging
import os
from typing import Any, Dict, Tuple

import socketio
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from aetherterm.agentserver.infrastructure import initialize_infra_services
from aetherterm.agentserver.infrastructure.config.di_container import setup_di_container

# Application services initialization removed - moved to domain
from aetherterm.agentserver.presentation.routes import router
from aetherterm.agentserver.presentation.web.config import (
    DEFAULT_CONFIG,
    parse_environment_config,
    setup_config_paths,
)

log = logging.getLogger("aetherterm.interfaces.web.app_factory")


class ASGIApplicationFactory:
    """Factory for creating ASGI applications with proper configuration."""

    def __init__(self):
        """Initialize the application factory."""
        self.di_container = None
        self.config = None

    def create_app(self, **kwargs) -> Tuple[Any, Any, Any, Dict]:
        """Create the AetherTerm AgentServer ASGI application with dependency injection."""
        # Initialize DI container
        self.di_container = setup_di_container()

        # Initialize services with DI
        initialize_infra_services(self.di_container.infrastructure)

        # Start with default config and override with provided kwargs
        self.config = DEFAULT_CONFIG.copy()
        self.config.update(kwargs)

        # Configure the dependency injection container
        from aetherterm.agentserver.containers import configure_container

        container = configure_container(self.config)

        # Create FastAPI application
        fastapi_app = self._create_fastapi_app()

        # Create Socket.IO server
        sio = self._create_socketio_server()

        # Create combined ASGI application
        asgi_app = self._create_combined_asgi_app(fastapi_app, sio)

        return asgi_app, sio, container, self.config

    def _create_fastapi_app(self) -> FastAPI:
        """Create and configure FastAPI application."""
        fastapi_app = FastAPI(
            title="AetherTerm AgentServer",
            description="Terminal server with AI agent integration",
            version="1.0.0",
        )

        # Add Gzip compression for better performance
        fastapi_app.add_middleware(GZipMiddleware, minimum_size=500)

        # Mount static files with optimizations
        static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
        if os.path.exists(static_path):
            fastapi_app.mount(
                "/static",
                StaticFiles(directory=static_path, html=True, check_dir=False),
                name="static",
            )
            log.info("Static files mounted from %s", static_path)

        # Include routers
        self._include_routers(fastapi_app)

        return fastapi_app

    def _include_routers(self, fastapi_app: FastAPI) -> None:
        """Include all application routers."""
        try:
            # Include main router
            fastapi_app.include_router(router)
            log.info("Main router included")

            # Include context inference router if available
            try:
                from aetherterm.agentserver.context_inference import context_api_router

                fastapi_app.include_router(context_api_router)
                log.info("Context inference router included")
            except ImportError:
                log.warning("Context inference router not available")

        except Exception as e:
            log.error("Error including routers: %s", e)
            raise

    def _create_socketio_server(self) -> socketio.AsyncServer:
        """Create and configure Socket.IO server."""
        sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins="*",
            logger=log.level <= logging.DEBUG,
            engineio_logger=log.level <= logging.DEBUG,
        )

        log.info("Socket.IO server created")
        return sio

    def _create_combined_asgi_app(self, fastapi_app: FastAPI, sio: socketio.AsyncServer) -> Any:
        """Create combined ASGI application with FastAPI and Socket.IO."""
        uri_root_path = self.config.get("uri_root_path", "")
        socketio_path = f"{uri_root_path}/socket.io" if uri_root_path else "/socket.io"

        asgi_app = socketio.ASGIApp(
            socketio_server=sio, other_asgi_app=fastapi_app, socketio_path=socketio_path
        )

        log.info("Combined ASGI application created with socketio_path: %s", socketio_path)
        return asgi_app


class LegacyApplicationFactory:
    """Legacy application factory for backward compatibility."""

    @staticmethod
    def create_app(**kwargs) -> Tuple[Any, Dict]:
        """Create the Butterfly ASGI application with dependency injection."""
        from aetherterm.agentserver.infrastructure.config.legacy_containers import (
            ApplicationContainer,
        )

        # Start with default config
        config = DEFAULT_CONFIG.copy()

        # Setup config paths first (may be overridden by kwargs)
        config = setup_config_paths(config)

        # Override with Click-provided values (this ensures CLI args take precedence)
        config.update(kwargs)

        # Configure the dependency injection container
        container = ApplicationContainer()
        container.config.from_dict(config)
        container.wire(
            modules=[
                "aetherterm.agentserver.server",
                "aetherterm.agentserver.terminals",
                "aetherterm.agentserver.utils",
                "aetherterm.agentserver.socket_handlers",
                "aetherterm.agentserver.routes",  # Wire routes module
            ]
        )

        return container, config


class ApplicationFactoryRegistry:
    """Registry for different application factory types."""

    _factories = {
        "default": ASGIApplicationFactory,
        "legacy": LegacyApplicationFactory,
    }

    @classmethod
    def get_factory(cls, factory_type: str = "default") -> Any:
        """Get application factory by type."""
        if factory_type not in cls._factories:
            raise ValueError(f"Unknown factory type: {factory_type}")
        return cls._factories[factory_type]()

    @classmethod
    def register_factory(cls, name: str, factory_class: type) -> None:
        """Register a new factory type."""
        cls._factories[name] = factory_class


def create_asgi_app_from_environment() -> Any:
    """
    Factory function for creating the ASGI application from environment.
    This is called by uvicorn/hypercorn when using:
    uvicorn aetherterm.agentserver.interfaces.web.config.app_factory:create_asgi_app_from_environment --factory
    """
    # Get configuration from environment variables
    config = parse_environment_config()

    # Create application using factory
    factory = ApplicationFactoryRegistry.get_factory("default")
    asgi_app, sio, container, final_config = factory.create_app(**config)

    log.info("ASGI application created from environment configuration")
    return asgi_app
