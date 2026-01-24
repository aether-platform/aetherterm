"""Workspace operation handlers."""

import logging
from uuid import uuid4
from .base import sio_instance, socket_error_handler, get_user_info_from_environ
from ..workspace_resume_service import resume_workspace_with_service

log = logging.getLogger("aetherterm.socket_handlers")


@socket_error_handler("workspace_error")
async def resume_workspace(sid, data):
    """Handle resuming an entire workspace with multiple tabs, panes and sessions."""
    await resume_workspace_with_service(sid, data, sio_instance)


@socket_error_handler("workspace_error")
async def on_workspace_connect(sid, data):
    """Handle user connection to the global workspace."""
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()

    # Get user info from environment to extract role
    environ = getattr(sio_instance, "environ", {}) if sio_instance else {}
    user_info = get_user_info_from_environ(environ)

    # Extract role from user info
    user_roles = user_info.get("roles", [])

    # Determine role: if "Viewer" is in roles, use that, otherwise default to "User"
    role = "Viewer" if "Viewer" in user_roles else "User"

    # Allow override from data if provided
    if "role" in data:
        role = data["role"]

    # Add user to global workspace
    service.add_user(sid, role)

    log.info(f"User {sid} ({role}) connected to global workspace with roles: {user_roles}")

    await sio_instance.emit("workspace_connected", {"success": True, "role": role}, room=sid)


@socket_error_handler("workspace_error")
async def workspace_get(sid, data):
    """Get the global workspace."""
    log.info(f"🔍 workspace_get called by {sid} with data: {data}")
    
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()
    workspace = service.get_workspace()

    log.info(f"User {sid} requested workspace data")
    log.info(
        f"Returning workspace: {workspace.get('id')} with {len(workspace.get('tabs', []))} tabs"
    )

    response = {"success": True, "workspace": workspace}
    log.info(f"📤 Emitting workspace_data to {sid}: {response}")

    await sio_instance.emit("workspace_data", response, room=sid)


@socket_error_handler("workspace_error")
async def on_workspace_create(sid, data):
    """Create workspace - returns the global workspace since we can't create new workspaces."""
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()

    # Check if user has permission to modify
    if not service.can_user_modify(sid):
        log.warning(f"User {sid} (Viewer) attempted to create workspace")
        await sio_instance.emit(
            "workspace_error", {"error": "Viewers cannot create workspaces"}, room=sid
        )
        return

    # We only have one global workspace, so return it
    workspace = service.get_workspace()

    log.info(f"User {sid} requested workspace creation - returning global workspace")

    await sio_instance.emit(
        "workspace_created", {"success": True, "workspace": workspace}, room=sid
    )


@socket_error_handler("workspace_error")
async def on_workspace_update(sid, data):
    """Update the global workspace."""
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()

    # Check if user has permission to modify
    if not service.can_user_modify(sid):
        log.warning(f"User {sid} (Viewer) attempted to update workspace")
        await sio_instance.emit(
            "workspace_error", {"error": "Viewers cannot update workspace"}, room=sid
        )
        return

    workspace_data = data.get("workspace", {})
    log.info(f"User {sid} updating workspace")

    # Update the workspace through the service
    updated_workspace = service.update_workspace(workspace_data)

    # Broadcast the update to all connected users
    await sio_instance.emit(
        "workspace_updated",
        {"workspace": updated_workspace},
    )

    log.info(f"Workspace updated by user {sid}")


@socket_error_handler("workspace_error")
async def tab_create(sid, data):
    """Handle creating a new tab in the global workspace."""
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()

    # Check if user has permission to modify
    if not service.can_user_modify(sid):
        log.warning(f"User {sid} (Viewer) attempted to create tab")
        await sio_instance.emit(
            "workspace_error", {"error": "Viewers cannot create tabs"}, room=sid
        )
        return

    # Extract tab data
    tab_data = data.get("tab", {})
    tab_id = tab_data.get("id") or str(uuid4())
    tab_title = tab_data.get("title", "New Tab")
    tab_type = tab_data.get("type", "terminal")

    log.info(f"Creating new tab: {tab_id} ({tab_type}) - '{tab_title}' for user {sid}")

    # Create the tab
    new_tab = {
        "id": tab_id,
        "title": tab_title,
        "type": tab_type,
        "active": True,
        "panes": [],
        "created_by": sid,
        "created_at": data.get("timestamp"),
    }

    # Add tab through service
    workspace = service.add_tab(new_tab)

    # Broadcast tab creation to all users
    await sio_instance.emit(
        "tab_created",
        {
            "success": True,
            "tab": new_tab,
            "workspace": workspace,
        },
    )

    log.info(f"Tab {tab_id} created successfully")


@socket_error_handler("workspace_error")
async def tab_close(sid, data):
    """Handle closing a tab in the global workspace."""
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    service = get_global_workspace_service()

    # Check if user has permission to modify
    if not service.can_user_modify(sid):
        log.warning(f"User {sid} (Viewer) attempted to close tab")
        await sio_instance.emit(
            "workspace_error", {"error": "Viewers cannot close tabs"}, room=sid
        )
        return

    tab_id = data.get("tabId")
    force_close = data.get("force", False)

    if not tab_id:
        await sio_instance.emit(
            "workspace_error", {"error": "tabId is required"}, room=sid
        )
        return

    log.info(f"Closing tab {tab_id} (force: {force_close}) for user {sid}")

    # Get the current workspace to check for associated sessions
    workspace = service.get_workspace()
    tab_to_close = None

    for tab in workspace.get("tabs", []):
        if tab["id"] == tab_id:
            tab_to_close = tab
            break

    if not tab_to_close:
        await sio_instance.emit(
            "workspace_error", {"error": f"Tab {tab_id} not found"}, room=sid
        )
        return

    # Clean up any terminal sessions associated with this tab
    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    sessions_to_close = []
    for pane in tab_to_close.get("panes", []):
        session_id = pane.get("sessionId")
        if session_id and session_id in AsyncioTerminal.sessions:
            sessions_to_close.append(session_id)

    # Close associated terminal sessions
    for session_id in sessions_to_close:
        try:
            terminal = AsyncioTerminal.sessions[session_id]
            await terminal.close()
            log.info(f"Closed terminal session {session_id} for tab {tab_id}")
        except Exception as e:
            log.error(f"Error closing terminal session {session_id}: {e}")

    # Remove the tab from workspace
    success = service.remove_tab(tab_id)

    if success:
        # Get updated workspace
        updated_workspace = service.get_workspace()

        # Broadcast tab closure to all users
        await sio_instance.emit(
            "tab_closed",
            {
                "success": True,
                "tabId": tab_id,
                "workspace": updated_workspace,
            },
            skip_sid=sid,  # Don't send to the user who closed it
        )
    else:
        await sio_instance.emit(
            "workspace_error",
            {"error": f"Failed to close tab {tab_id}"},
            room=sid,
        )