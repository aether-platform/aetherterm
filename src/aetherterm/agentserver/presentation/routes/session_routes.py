"""
Session Routes - Session Management Endpoints

Provides session-related routes for listing and managing terminal sessions.
"""

import logging

# from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

# Initialize router
router = APIRouter()
log = logging.getLogger("aetherterm.routes.session")


@router.get("/sessions/list.json")
async def sessions_list(request: Request) -> JSONResponse:
    """Get the list of active sessions."""
    # Check if remote authentication is being used
    is_remote_authentication = bool(
        request.headers.get("authorization")
        or request.headers.get("x-forwarded-proto") == "https"
        or request.headers.get("x-forwarded-for")
        or request.cookies.get("session")
        or request.cookies.get("auth_token")
    )

    # Security check: prevent access in unsecure mode without remote authentication
    unsecure = config.get("unsecure", False)
    if unsecure and not is_remote_authentication:
        raise HTTPException(
            status_code=403, detail="Not available in unsecure mode without remote authentication"
        )

    # TODO: Implement proper session listing when terminal sessions are implemented
    # For now, return empty list
    return JSONResponse({"sessions": [], "user": "unknown"})
