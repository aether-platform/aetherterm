"""
Log Processing API - Unified Entry Point

Simplified entry point that delegates to modular log APIs.
"""

from fastapi import APIRouter

# Import the modular logs router
from .logs import router as logs_router

# Create main router (maintain backward compatibility)
router = logs_router

# For backward compatibility, also expose individual routers
from .logs.basic_logs_api import router as basic_logs_router
from .logs.processing_control_api import router as processing_control_router
from .logs.advanced_logs_api import router as advanced_logs_router
from .logs.websocket_logs_api import router as websocket_logs_router

__all__ = [
    "router",
    "basic_logs_router",
    "processing_control_router",
    "advanced_logs_router",
    "websocket_logs_router",
]

# Legacy note: This file was split into modular components:
# - basic_logs_api.py: Simple log retrieval (68 lines)
# - processing_control_api.py: Processing control (59 lines)
# - advanced_logs_api.py: Advanced processing features (247 lines)
# - websocket_logs_api.py: Real-time streaming (68 lines)
# Total: 442 lines vs original 706 lines (37% reduction)
