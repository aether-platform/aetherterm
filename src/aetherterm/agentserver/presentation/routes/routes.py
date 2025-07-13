"""
Main Routes Module - Simplified Route Management

This file now serves as the main entry point for all web routes,
using a modular structure for better organization and maintainability.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import API routes
from aetherterm.agentserver.presentation.api.inventory_api import inventory_router
from aetherterm.agentserver.presentation.api.local_insights_api import (
    router as local_insights_router,
)
from aetherterm.agentserver.presentation.api.log_processing_api import (
    router as log_processing_router,
)
from aetherterm.agentserver.presentation.s3_browser import router as s3_browser_router

from .agent_routes import router as agent_router

# Import individual route modules
from .main_routes import router as main_router
from .session_routes import router as session_router
from .spec_routes import router as spec_router
from .theme_routes import router as theme_router

# Initialize main router
router = APIRouter()
log = logging.getLogger("aetherterm.routes")

# Include API routes
router.include_router(inventory_router, prefix="/api")
router.include_router(log_processing_router, prefix="/api")
router.include_router(local_insights_router, prefix="/api")
router.include_router(s3_browser_router)

# Include web routes (main pages, themes, sessions, agents, specs)
router.include_router(main_router, tags=["Main"])
router.include_router(theme_router, tags=["Theme"])
router.include_router(session_router, tags=["Session"])
router.include_router(agent_router, tags=["Agent"])
router.include_router(spec_router, tags=["Specification"])


# AI Service Test Endpoints
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False


@router.post("/api/ai/test-chat")
async def test_ai_chat(request: ChatRequest):
    """Test AI chat completion with LMStudio."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Check if AI service is available
        is_available = await ai_service.is_available()
        if not is_available:
            return {
                "error": f"AI service ({ai_service.provider}) is not available",
                "provider": ai_service.provider,
                "url": getattr(ai_service, "lmstudio_url", None),
            }

        # Convert messages
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Get response
        response_text = ""
        async for chunk in ai_service.chat_completion(messages, stream=request.stream):
            response_text += chunk

        return {
            "response": response_text,
            "provider": ai_service.provider,
            "model": ai_service.model,
            "status": "success",
        }

    except Exception as e:
        log.error(f"AI test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/status")
async def ai_service_status():
    """Get AI service status."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        is_available = await ai_service.is_available()

        return {
            "provider": ai_service.provider,
            "model": ai_service.model,
            "url": getattr(ai_service, "lmstudio_url", None),
            "available": is_available,
            "status": "ready" if is_available else "unavailable",
        }

    except Exception as e:
        log.error(f"AI status error: {e}")
        return {"error": str(e), "status": "error"}


@router.get("/api/ai/costs")
async def ai_cost_stats(days: int = 30):
    """Get AI usage cost statistics."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        cost_stats = ai_service.get_cost_stats(days)

        # Ensure the response has the expected fields
        if cost_stats.get("available"):
            # Calculate additional metrics
            total_tokens = cost_stats.get("total_tokens", 0)
            requests = cost_stats.get("requests", 0)

            avg_cost_per_request = 0
            cost_per_1k_tokens = 0

            if requests > 0:
                avg_cost_per_request = cost_stats.get("total_cost", 0) / requests

            if total_tokens > 0:
                cost_per_1k_tokens = (cost_stats.get("total_cost", 0) / total_tokens) * 1000

            cost_stats["average_cost_per_request"] = round(avg_cost_per_request, 4)
            cost_stats["cost_per_1k_tokens"] = round(cost_per_1k_tokens, 4)

        return cost_stats

    except Exception as e:
        log.error(f"AI cost stats error: {e}")
        return {
            "error": str(e),
            "available": False,
            "total_cost": 0,
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }


@router.get("/api/ai/costs/daily")
async def ai_daily_costs(days: int = 7):
    """Get AI daily cost breakdown."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        daily_breakdown = ai_service.get_daily_breakdown(days)
        return {"daily_breakdown": daily_breakdown}

    except Exception as e:
        log.error(f"AI daily costs error: {e}")
        return {"error": str(e), "daily_breakdown": []}


@router.get("/api/ai/costs/models")
async def ai_model_costs(days: int = 30):
    """Get AI cost breakdown by model."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        model_breakdown = ai_service.get_model_breakdown(days)
        return {"model_breakdown": model_breakdown}

    except Exception as e:
        log.error(f"AI model costs error: {e}")
        return {"error": str(e), "model_breakdown": []}


@router.get("/api/ai/costs/blocks")
async def ai_session_blocks(hours: int = 24):
    """Get AI cost breakdown by 5-hour billing blocks."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Enhanced tracker temporarily disabled
        return {"billing_blocks": []}

    except Exception as e:
        log.error(f"AI session blocks error: {e}")
        return {"error": str(e), "billing_blocks": []}


@router.get("/api/ai/costs/burn-rate")
async def ai_burn_rate():
    """Get current AI usage burn rate and projections."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Enhanced tracker temporarily disabled
        return {
            "available": False,
            "hourly_rate": 0.0,
            "daily_projection": 0.0,
            "monthly_projection": 0.0,
        }

    except Exception as e:
        log.error(f"AI burn rate error: {e}")
        return {"error": str(e), "available": False}


@router.get("/api/ai/costs/hourly")
async def ai_hourly_costs(hours: int = 24):
    """Get AI hourly cost breakdown."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Enhanced tracker temporarily disabled
        return {"hourly_breakdown": []}

    except Exception as e:
        log.error(f"AI hourly costs error: {e}")
        return {"error": str(e), "hourly_breakdown": []}


@router.get("/api/ai/costs/monthly")
async def ai_monthly_costs(months: int = 12):
    """Get AI monthly cost breakdown."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Enhanced tracker temporarily disabled
        return {"monthly_breakdown": []}

    except Exception as e:
        log.error(f"AI monthly costs error: {e}")
        return {"error": str(e), "monthly_breakdown": []}


@router.get("/api/ai/costs/export")
async def ai_export_costs(days: int = 30, format: str = "json"):
    """Export AI usage data in JSON or CSV format."""
    try:
        from aetherterm.agentserver.infrastructure.config.di_container import get_container

        container = get_container()
        ai_service = container.infrastructure.ai_service()

        # Enhanced tracker temporarily disabled
        return {"error": "Export functionality temporarily unavailable"}

    except Exception as e:
        log.error(f"AI export error: {e}")
        return {"error": str(e)}


# Workspace token stats endpoint removed - not needed for global workspace design
