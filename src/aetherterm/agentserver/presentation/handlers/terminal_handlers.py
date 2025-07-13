"""
Terminal WebSocket Handlers - Interface Layer

Terminal session management handlers with Dependency Injection.
"""

import logging
from uuid import uuid4

# from dependency_injector.wiring import inject, Provide

# from aetherterm.agentserver.infrastructure.config.di_container import MainContainer

log = logging.getLogger("aetherterm.handlers.terminal")


async def connect(sid, environ, sio_instance):
    """Handle client connection."""
    log.info(f"Client connected: {sid}")
    await sio_instance.emit("connected", {"data": "Connected to Butterfly"}, room=sid)


# @inject
async def disconnect(
    sid,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Handle client disconnection."""
    log.info(f"Client disconnected: {sid}")

    # Clean up client sessions using injected service
    # workspace_service.cleanup_client_sessions(sid)
    # Temporarily disabled cleanup


# @inject
async def create_terminal(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Create a new terminal session or reconnect to existing one."""
    try:
        session_id = data.get("session") or f"terminal_{uuid4().hex[:8]}"
        tab_id = data.get("tabId", "default")
        pane_id = data.get("paneId", "default")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)
        is_reconnect = data.get("reconnect", False)

        log.info(f"Terminal request - Session: {session_id}, SID: {sid}, Reconnect: {is_reconnect}")

        # Use injected workspace service for terminal creation/reconnection
        # if is_reconnect:
        #     result = await workspace_service.reconnect_terminal(
        #         client_sid=sid,
        #         session_id=session_id,
        #         cols=cols,
        #         rows=rows,
        #     )
        # else:
        #     result = await workspace_service.create_terminal(
        #         client_sid=sid,
        #         session_id=session_id,
        #         tab_id=tab_id,
        #         pane_id=pane_id,
        #         cols=cols,
        #         rows=rows,
        #     )

        # Temporary mock result
        result = {
            "session": session_id,  # Changed from session_id to session to match frontend expectation
            "tab_id": tab_id,
            "pane_id": pane_id,
            "cols": cols,
            "rows": rows,
            "reconnected": is_reconnect,
            "status": "mock_ready",
        }

        await sio_instance.emit("terminal_ready", result, room=sid)
        log.info(f"Terminal ready event sent for session: {session_id}")

    except Exception as e:
        log.error(f"Failed to create terminal: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


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
async def terminal_input(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Handle terminal input."""
    try:
        session_id = data.get("session")
        input_data = data.get("data", "")

        if session_id:
            # success = await workspace_service.terminal_input(session_id, input_data)
            success = False  # Temporarily disabled terminal input
            if not success:
                await sio_instance.emit("error", {"message": "Failed to send input"}, room=sid)

    except Exception as e:
        log.error(f"Failed to handle terminal input: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)


# @inject
async def terminal_resize(
    sid,
    data,
    sio_instance,
    # workspace_service: WorkspaceService = Provide[MainContainer.application.workspace_service]
):
    """Handle terminal resize."""
    try:
        session_id = data.get("session")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        if session_id:
            # success = await workspace_service.terminal_resize(session_id, cols, rows)
            success = False  # Temporarily disabled terminal resize
            if not success:
                await sio_instance.emit("error", {"message": "Failed to resize terminal"}, room=sid)

    except Exception as e:
        log.error(f"Failed to handle terminal resize: {e}")
        await sio_instance.emit("error", {"message": str(e)}, room=sid)
