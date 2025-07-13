"""
Routes Package - Modular Route Organization

Provides centralized route management with separation of concerns.
"""

from fastapi import APIRouter

from .agent_routes import router as agent_router
from .main_routes import router as main_router
from .session_routes import router as session_router
from .spec_routes import router as spec_router
from .theme_routes import router as theme_router

# Main router that includes all sub-routers
router = APIRouter()

# Include all route modules
router.include_router(main_router, tags=["Main"])
router.include_router(theme_router, tags=["Theme"])
router.include_router(session_router, tags=["Session"])
router.include_router(agent_router, tags=["Agent"])
router.include_router(spec_router, tags=["Specification"])

__all__ = ["router"]
