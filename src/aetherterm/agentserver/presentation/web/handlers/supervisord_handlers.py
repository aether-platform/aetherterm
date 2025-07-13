"""
Supervisord MCP Socket.IO Handlers

Provides WebSocket handlers for supervisord process management via MCP protocol.
"""

import logging
from typing import Any, Dict

from aetherterm.agentserver.infrastructure.external.supervisord_mcp_service import (
    get_supervisord_mcp_service,
)

log = logging.getLogger(__name__)


async def get_processes_list(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Get list of all processes managed by supervisord."""
    try:
        service = get_supervisord_mcp_service()
        processes = await service.get_process_list()

        return {"status": "ok", "processes": processes}
    except Exception as e:
        log.error(f"Error getting processes list: {e}")
        return {"status": "error", "message": str(e)}


async def start_process(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Start a specific process."""
    try:
        process_name = data.get("name")
        if not process_name:
            return {"status": "error", "message": "Process name is required"}

        service = get_supervisord_mcp_service()
        result = await service.start_process(process_name)

        return result
    except Exception as e:
        log.error(f"Error starting process: {e}")
        return {"status": "error", "message": str(e)}


async def stop_process(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Stop a specific process."""
    try:
        process_name = data.get("name")
        if not process_name:
            return {"status": "error", "message": "Process name is required"}

        service = get_supervisord_mcp_service()
        result = await service.stop_process(process_name)

        return result
    except Exception as e:
        log.error(f"Error stopping process: {e}")
        return {"status": "error", "message": str(e)}


async def restart_process(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Restart a specific process."""
    try:
        process_name = data.get("name")
        if not process_name:
            return {"status": "error", "message": "Process name is required"}

        service = get_supervisord_mcp_service()
        result = await service.restart_process(process_name)

        return result
    except Exception as e:
        log.error(f"Error restarting process: {e}")
        return {"status": "error", "message": str(e)}


async def get_process_logs(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Get logs for a specific process."""
    try:
        process_name = data.get("name")
        if not process_name:
            return {"status": "error", "message": "Process name is required"}

        lines = data.get("lines", 100)

        service = get_supervisord_mcp_service()
        result = await service.get_process_logs(process_name, lines)

        return result
    except Exception as e:
        log.error(f"Error getting process logs: {e}")
        return {"status": "error", "message": str(e)}


async def get_supervisord_status(sid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Get status of supervisord MCP integration."""
    try:
        service = get_supervisord_mcp_service()
        status = await service.get_status()

        return {"status": "ok", "supervisord": status}
    except Exception as e:
        log.error(f"Error getting supervisord status: {e}")
        return {"status": "error", "message": str(e)}
