"""
Processing Control API - Log Processing Management

Provides endpoints for controlling log processing tasks.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger("aetherterm.api.logs.processing")

# Initialize router
router = APIRouter()


@router.post("/start-processing")
async def start_log_processing() -> JSONResponse:
    """Start the log processing task."""
    try:
        await AsyncioTerminal.start_log_processing()
        return JSONResponse({"status": "success", "message": "Log processing started"})
    except Exception as e:
        log.error(f"Error starting log processing: {e}")
        raise HTTPException(status_code=500, detail="Failed to start log processing")


@router.post("/stop-processing")
async def stop_log_processing() -> JSONResponse:
    """Stop the log processing task."""
    try:
        await AsyncioTerminal.stop_log_processing()
        return JSONResponse({"status": "success", "message": "Log processing stopped"})
    except Exception as e:
        log.error(f"Error stopping log processing: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop log processing")


@router.get("/processing-status")
async def get_processing_status() -> JSONResponse:
    """Get the current status of log processing."""
    try:
        is_running = (
            AsyncioTerminal.log_processing_task is not None
            and not AsyncioTerminal.log_processing_task.done()
        )

        status = {
            "running": is_running,
            "buffer_size": len(AsyncioTerminal.log_buffer),
            "processed_count": len(AsyncioTerminal.processed_logs),
            "subscribers": len(AsyncioTerminal.log_subscribers),
        }

        return JSONResponse(status)
    except Exception as e:
        log.error(f"Error getting processing status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get processing status")
