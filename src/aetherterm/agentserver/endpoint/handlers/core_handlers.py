"""
Core WebSocket Handlers - Interface Layer

Core terminal functionality and basic operations with Dependency Injection.
"""

import logging
from datetime import datetime
# from dependency_injector.wiring import inject, Provide

from aetherterm.agentserver.domain.services.workspace_service import WorkspaceService
# from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

log = logging.getLogger("aetherterm.handlers.core")

# Global storage for socket.io server instance
sio_instance = None


def set_sio_instance(sio):
    """Set the global socket.io server instance."""
    global sio_instance
    sio_instance = sio
    log.info("Socket.IO instance configured for core handlers")


def broadcast_to_session(session_id, message):
    """Broadcast message to all clients connected to a session."""
    try:
        if sio_instance:
            sio_instance.emit(
                "session_broadcast",
                {
                    "session_id": session_id,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        else:
            log.warning("Socket.IO instance not available for broadcast")

    except Exception as e:
        log.error(f"Failed to broadcast to session {session_id}: {e}")


# @inject
async def system_status(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Get system status information."""
    try:
        # Get system status from workspace service
        # status = await workspace_service.get_system_status()
        status = {"status": "ok", "disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit(
            "system_status",
            {"status": status, "timestamp": datetime.utcnow().isoformat()},
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to get system status: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def ping(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Handle ping requests for connection testing."""
    try:
        client_timestamp = data.get("timestamp")
        server_timestamp = datetime.utcnow().isoformat()

        await sio_instance.emit(
            "pong",
            {
                "client_timestamp": client_timestamp,
                "server_timestamp": server_timestamp,
                "roundtrip_start": server_timestamp,
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to handle ping: {e}")


# @inject
async def get_session_info(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Get information about current session."""
    try:
        session_id = data.get("session_id")

        # Get session info from workspace service
        # session_info = await workspace_service.get_session_info(session_id)
        session_info = {"disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit(
            "session_info",
            {
                "session_id": session_id,
                "info": session_info,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to get session info: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def list_sessions(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """List all available sessions for current user."""
    try:
        # Get session list from workspace service
        # sessions = await workspace_service.list_user_sessions(sid)
        sessions = []

        await sio_instance.emit(
            "sessions_list",
            {
                "sessions": sessions,
                "count": len(sessions),
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to list sessions: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def cleanup_session(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Clean up a specific session."""
    try:
        session_id = data.get("session_id")
        force = data.get("force", False)

        if not session_id:
            await sio_instance.emit("error", {"message": "Session ID required"}, room=sid)
            return

        # Clean up session through workspace service
        # result = await workspace_service.cleanup_session(session_id, force=force)
        result = True

        await sio_instance.emit(
            "session_cleaned",
            {
                "session_id": session_id,
                "success": result,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to cleanup session: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def get_resource_usage(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Get current resource usage statistics."""
    try:
        # Get resource usage from workspace service
        # usage = await workspace_service.get_resource_usage()
        usage = {"disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit(
            "resource_usage", {"usage": usage, "timestamp": datetime.utcnow().isoformat()}, room=sid
        )

    except Exception as e:
        log.error(f"Failed to get resource usage: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


async def handle_client_error(sid, data, sio_instance):
    """Handle client-side error reports."""
    try:
        error_type = data.get("type")
        error_message = data.get("message")
        stack_trace = data.get("stack")

        log.error(f"Client error from {sid}: {error_type} - {error_message}")
        if stack_trace:
            log.debug(f"Client stack trace: {stack_trace}")

        # Acknowledge error receipt
        await sio_instance.emit(
            "error_acknowledged",
            {"type": error_type, "timestamp": datetime.utcnow().isoformat()},
            room=sid,
        )

    except Exception as e:
        log.error(f"Failed to handle client error: {e}")


async def broadcast_system_notification(notification_type, message, data=None):
    """Broadcast system-wide notifications."""
    try:
        if sio_instance:
            notification = {
                "type": notification_type,
                "message": message,
                "data": data or {},
                "timestamp": datetime.utcnow().isoformat(),
            }

            await sio_instance.emit("system_notification", notification)
            log.info(f"Broadcasted system notification: {notification_type}")
        else:
            log.warning("Socket.IO instance not available for system notification")

    except Exception as e:
        log.error(f"Failed to broadcast system notification: {e}")
