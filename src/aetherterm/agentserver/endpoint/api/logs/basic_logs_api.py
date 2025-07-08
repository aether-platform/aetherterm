"""
Basic Logs API - Simple Log Retrieval

Provides basic REST endpoints for log retrieval and statistics.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger("aetherterm.api.logs.basic")

# Initialize router
router = APIRouter()


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of recent logs to retrieve"),
    category: Optional[str] = Query(None, description="Filter by log category"),
) -> JSONResponse:
    """Get recent processed logs with optional filtering."""
    try:
        logs = AsyncioTerminal.get_recent_logs(limit=limit, category=category)
        return JSONResponse(
            {"logs": logs, "count": len(logs), "limit": limit, "category": category}
        )
    except Exception as e:
        log.error(f"Error retrieving recent logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve logs")


@router.get("/statistics")
async def get_log_statistics() -> JSONResponse:
    """Get statistics about processed logs."""
    try:
        stats = AsyncioTerminal.get_log_statistics()
        return JSONResponse(stats)
    except Exception as e:
        log.error(f"Error retrieving log statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/categories")
async def get_log_categories() -> JSONResponse:
    """Get available log categories with descriptions."""
    try:
        categories = {
            "error": "Error messages and exceptions",
            "warning": "Warning messages and deprecation notices",
            "info": "Informational messages and status updates",
            "success": "Success messages and completion notices",
            "command": "Shell commands and prompts",
            "system": "System-level messages and kernel output",
            "general": "General output and uncategorized messages",
        }
        return JSONResponse({"categories": categories})
    except Exception as e:
        log.error(f"Error retrieving log categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve categories")


def get_category_description(category: str) -> str:
    """Get description for a specific log category."""
    descriptions = {
        "error": "Error messages and exceptions",
        "warning": "Warning messages and deprecation notices",
        "info": "Informational messages and status updates",
        "success": "Success messages and completion notices",
        "command": "Shell commands and prompts",
        "system": "System-level messages and kernel output",
        "general": "General output and uncategorized messages",
    }
    return descriptions.get(category, "Unknown category")
