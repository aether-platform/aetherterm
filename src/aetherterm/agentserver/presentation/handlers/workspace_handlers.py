"""
Workspace WebSocket Handlers - Interface Layer

Workspace session and tab management handlers with Dependency Injection.
"""

import logging
from datetime import datetime

# from dependency_injector.wiring import inject, Provide

# from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

log = logging.getLogger("aetherterm.handlers.workspace")


# @inject
async def resume_workspace(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Resume a workspace with multiple terminals."""
    try:
        workspace_id = data.get("workspaceId", "default")
        tabs = data.get("tabs", [])

        # Use injected workspace service for workspace resumption
        # result = await workspace_service.resume_workspace(
        #     client_sid=sid, workspace_id=workspace_id, tabs=tabs
        # )
        result = {
            "workspace_id": workspace_id,
            "tabs": tabs,
            "disabled": "dependency injection temporarily disabled",
        }

        await sio_instance.emit("workspace_resumed", result, room=sid)

    except Exception as e:
        log.error(f"Failed to resume workspace: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def resume_terminal(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Resume a specific terminal session."""
    try:
        session_id = data.get("session")
        tab_id = data.get("tabId", "default")
        pane_id = data.get("paneId", "default")

        if not session_id:
            await sio_instance.emit("error", {"message": "Session ID required"}, room=sid)
            return

        # Use injected workspace service for terminal resumption
        # result = await workspace_service.resume_terminal(
        #     client_sid=sid,
        #     session_id=session_id,
        #     tab_id=tab_id,
        #     pane_id=pane_id,
        # )
        result = {
            "session_id": session_id,
            "tab_id": tab_id,
            "pane_id": pane_id,
            "disabled": "dependency injection temporarily disabled",
        }

        await sio_instance.emit("terminal_resumed", result, room=sid)

    except Exception as e:
        log.error(f"Failed to resume terminal: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def wrapper_session_sync(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Synchronize wrapper session state."""
    try:
        sessions = data.get("sessions", {})

        # Update session states in workspace service
        # result = await workspace_service.sync_wrapper_sessions(sid, sessions)
        result = {"sessions": sessions, "disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit("wrapper_session_synced", result, room=sid)

    except Exception as e:
        log.error(f"Failed to sync wrapper sessions: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def get_wrapper_sessions(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Get current wrapper session information."""
    try:
        # Get session information from workspace service
        # result = await workspace_service.get_wrapper_sessions(sid)
        result = {"disabled": "dependency injection temporarily disabled"}

        await sio_instance.emit("wrapper_sessions_info", result, room=sid)

    except Exception as e:
        log.error(f"Failed to get wrapper sessions: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


def get_terminal_context(session_id):
    """Get terminal context for session."""
    try:
        # This would typically query the workspace service for context
        # For now, return basic context information
        return {
            "session_id": session_id,
            "working_directory": "/",
            "shell": "/bin/bash",
            "environment": {},
            "history": [],
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        log.error(f"Failed to get terminal context for {session_id}: {e}")
        return None
