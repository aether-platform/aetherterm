"""
WebSocket Handlers Package - Interface Layer

Modular WebSocket handlers organized by functionality with Clean Architecture
and Dependency Injection patterns.
"""

from . import terminal_handlers
from . import agent_handlers
from . import workspace_handlers
from . import log_handlers
from . import auth_handlers
from . import ai_handlers
from . import core_handlers

__all__ = [
    "terminal_handlers",
    "agent_handlers",
    "workspace_handlers",
    "log_handlers",
    "auth_handlers",
    "ai_handlers",
    "core_handlers",
]
