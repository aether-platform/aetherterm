"""
Logs API Package - Modular Log Management

Provides organized log management APIs with separation of concerns.
"""

from fastapi import APIRouter

from .basic_logs_api import router as basic_router
from .processing_control_api import router as processing_router
from .advanced_logs_api import router as advanced_router
from .websocket_logs_api import router as websocket_router

# Main logs router that includes all sub-routers
router = APIRouter(prefix="/api/logs", tags=["logs"])

# Include all log-related route modules
router.include_router(basic_router, prefix="/basic", tags=["Basic Logs"])
router.include_router(processing_router, prefix="/processing", tags=["Log Processing"])
router.include_router(advanced_router, prefix="/advanced", tags=["Advanced Logs"])
router.include_router(websocket_router, prefix="/ws", tags=["WebSocket Logs"])

__all__ = ["router"]
