"""
Infrastructure Layer Facade

Provides unified access to all infrastructure services with DI integration.
"""

from dependency_injector.wiring import Provide, inject
from .external.ai_service import AIService
from .external.security_service import SecurityService
from .persistence.memory_store import MemoryStore
from .config.ssl_config import SSLConfig


class InfrastructureServices:
    """Unified access to all infrastructure services."""

    @inject
    def __init__(
        self,
        ai_service: AIService = Provide["infrastructure.ai_service"],
        security_service: SecurityService = Provide["infrastructure.security_service"],
        memory_store: MemoryStore = Provide["infrastructure.memory_store"],
        ssl_config: SSLConfig = Provide["infrastructure.ssl_config"],
    ):
        self.ai_service = ai_service
        self.security_service = security_service
        self.memory_store = memory_store
        self.ssl_config = ssl_config


# Global instance for easy access (with fallback)
infra_services = None


def initialize_infra_services(container=None):
    """Initialize infrastructure services with DI container."""
    global infra_services
    if container:
        infra_services = InfrastructureServices()
        container.wire(modules=[__name__])
    else:
        # Fallback without DI
        infra_services = InfrastructureServicesFallback()


class InfrastructureServicesFallback:
    """Fallback infrastructure services without DI."""

    def __init__(self):
        self.ai_service = AIService()
        self.security_service = SecurityService()
        self.memory_store = MemoryStore()
        self.ssl_config = SSLConfig()


# Initialize fallback services immediately
if infra_services is None:
    infra_services = InfrastructureServicesFallback()


# Helper functions for backward compatibility
def get_ai_service() -> AIService:
    """Get AI service instance."""
    return infra_services.ai_service if infra_services else AIService()


def get_security_service() -> SecurityService:
    """Get security service instance."""
    return infra_services.security_service if infra_services else SecurityService()


def set_socket_io_instance(sio):
    """Set Socket.IO instance for infrastructure services."""
    if infra_services:
        infra_services.security_service.set_socket_io_instance(sio)
