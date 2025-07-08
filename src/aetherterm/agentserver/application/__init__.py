"""
Application Layer Facade

Provides unified access to all application services with DI integration.
"""

from dependency_injector.wiring import Provide, inject
from aetherterm.agentserver.domain.services.workspace_service import WorkspaceService
from aetherterm.agentserver.domain.services.agent_service import AgentService
from aetherterm.agentserver.domain.services.report_service import ReportService


class ApplicationServices:
    """Unified access to all application services."""

    @inject
    def __init__(
        self,
        workspace_service: WorkspaceService = Provide["application.workspace_service"],
        agent_service: AgentService = Provide["application.agent_service"],
        report_service: ReportService = Provide["application.report_service"],
    ):
        self.workspace = workspace_service
        self.agents = agent_service
        self.reports = report_service


# Global instance for easy access (with fallback)
app_services = None


def initialize_app_services(container=None):
    """Initialize application services with DI container."""
    global app_services
    if container:
        app_services = ApplicationServices()
        container.wire(modules=[__name__])
    else:
        # Fallback without DI
        app_services = ApplicationServicesFallback()


class ApplicationServicesFallback:
    """Fallback application services without DI."""

    def __init__(self):
        self.workspace = WorkspaceService()
        self.agents = AgentService()
        self.reports = ReportService()


# Initialize fallback services immediately
if app_services is None:
    app_services = ApplicationServicesFallback()
