"""Connection management handlers."""

import asyncio
import logging
from .base import sio_instance, get_user_info_from_environ

log = logging.getLogger("aetherterm.socket_handlers")


async def connect(sid, environ, auth=None):
    """Handle client connection."""
    log.info(f"🔌 CLIENT CONNECT: {sid}")
    log.info(f"🔌 ENVIRON: {environ.get('HTTP_USER_AGENT', 'No User Agent')}")
    log.info(f"🔌 AUTH: {auth}")

    # Extract user info from environment to determine role
    try:
        user_info = get_user_info_from_environ(environ)
        user_roles = user_info.get("roles", [])
        role = "Viewer" if "Viewer" in user_roles else "User"
        log.info(f"🔌 USER INFO: {user_info}")
        log.info(f"🔌 USER ROLE: {role}")
    except Exception as e:
        log.error(f"🔌 ERROR getting user info: {e}")
        user_roles = []
        role = "User"

    # Add user to global workspace
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    global_service = get_global_workspace_service()
    global_service.add_user(sid, role)
    log.info(f"Added user {sid} to global workspace with role: {role}")

    await sio_instance.emit("connected", {"data": "Connected to Butterfly"}, room=sid)

    try:
        # Simple welcome message instead of file-based MOTD
        motd_content = "Welcome to AetherTerm - AI Terminal Platform\r\n"

        await sio_instance.emit(
            "terminal_output", {"session": "motd", "data": motd_content}, room=sid
        )
    except Exception as e:
        log.error(f"Error sending MOTD: {e}")


async def disconnect(sid, environ=None):
    """Handle client disconnection."""
    log.info(f"Client disconnected: {sid}")

    # Remove user from global workspace
    from aetherterm.agentserver.domain.services.global_workspace_service import (
        get_global_workspace_service,
    )

    global_service = get_global_workspace_service()
    global_service.remove_user(sid)

    # Remove client from any terminal sessions and schedule delayed closure if no clients remain
    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    for session_id, terminal in list(AsyncioTerminal.sessions.items()):
        if hasattr(terminal, "client_sids") and sid in terminal.client_sids:
            terminal.client_sids.discard(sid)
            log.info(f"Removed client {sid} from terminal session {session_id}")
            # If no clients remain, schedule delayed terminal closure
            if not terminal.client_sids:
                log.info(
                    f"No clients remaining for session {session_id}, scheduling delayed closure"
                )
                # Add a grace period of 30 seconds for reconnection
                await _schedule_terminal_closure(session_id, terminal, grace_period=30)


async def _schedule_terminal_closure(session_id: str, terminal, grace_period: int = 30):
    """Schedule terminal closure after a grace period, cancelling if clients reconnect."""
    # Cancel existing closure task if any
    if hasattr(terminal, "_closure_task") and terminal._closure_task:
        terminal._closure_task.cancel()

    # Create new closure task
    terminal._closure_task = asyncio.create_task(
        _delayed_terminal_closure(session_id, terminal, grace_period)
    )


async def _delayed_terminal_closure(session_id: str, terminal, grace_period: int):
    """Delayed terminal closure implementation."""
    try:
        log.info(f"Waiting {grace_period}s before closing terminal session {session_id}")
        await asyncio.sleep(grace_period)

        # Check if clients have reconnected
        if hasattr(terminal, "client_sids") and terminal.client_sids:
            log.info(f"Clients reconnected to session {session_id}, cancelling closure")
            return

        # Close the terminal
        log.info(f"Closing idle terminal session {session_id}")
        try:
            await terminal.close()
        except Exception as e:
            log.error(f"Error closing terminal session {session_id}: {e}")

        # Clean up session data
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
        
        if session_id in AsyncioTerminal.sessions:
            del AsyncioTerminal.sessions[session_id]

        if session_id in AsyncioTerminal.session_buffers:
            del AsyncioTerminal.session_buffers[session_id]

        if session_id in AsyncioTerminal.session_owners:
            del AsyncioTerminal.session_owners[session_id]

        log.info(f"Terminal session {session_id} closed and cleaned up")

    except asyncio.CancelledError:
        log.info(f"Terminal closure for session {session_id} was cancelled")
    except Exception as e:
        log.error(f"Error in delayed terminal closure for session {session_id}: {e}")


async def reconnect_session(sid, data):
    """Handle session reconnection."""
    session_id = data.get("session_id")
    if not session_id:
        await sio_instance.emit(
            "reconnect_error", {"error": "session_id required"}, room=sid
        )
        return

    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    # Check if session exists
    if session_id not in AsyncioTerminal.sessions:
        await sio_instance.emit(
            "reconnect_error", {"error": f"Session {session_id} not found"}, room=sid
        )
        return

    terminal = AsyncioTerminal.sessions[session_id]

    # Validate session ownership
    from .base import get_user_info_from_environ, check_session_ownership
    
    user_info = get_user_info_from_environ(data.get("environ", {}))
    if not check_session_ownership(session_id, user_info):
        await sio_instance.emit(
            "reconnect_error", {"error": "Access denied to session"}, room=sid
        )
        return

    # Add client to session
    if not hasattr(terminal, "client_sids"):
        terminal.client_sids = set()
    terminal.client_sids.add(sid)

    # Cancel any pending closure
    if hasattr(terminal, "_closure_task") and terminal._closure_task:
        terminal._closure_task.cancel()
        terminal._closure_task = None

    # Join session room
    room_name = f"session_{session_id}"
    await sio_instance.enter_room(sid, room_name)

    # Send session history
    await send_terminal_history(sid, session_id, terminal)

    await sio_instance.emit(
        "session_reconnected",
        {
            "session_id": session_id,
            "message": "Successfully reconnected to session",
        },
        room=sid,
    )

    log.info(f"Client {sid} reconnected to session {session_id}")


async def send_terminal_history(sid, session_id, terminal):
    """Send terminal history to reconnecting client."""
    try:
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
        
        # Send buffered output if available
        if session_id in AsyncioTerminal.session_buffers:
            buffer_data = AsyncioTerminal.session_buffers[session_id]
            if buffer_data:
                await sio_instance.emit(
                    "terminal_output",
                    {"session": session_id, "data": buffer_data},
                    room=sid,
                )
                log.info(f"Sent {len(buffer_data)} bytes of buffered data to {sid}")

        # Send current terminal state
        if hasattr(terminal, "get_current_state"):
            try:
                state = await terminal.get_current_state()
                if state:
                    await sio_instance.emit(
                        "terminal_state",
                        {"session": session_id, "state": state},
                        room=sid,
                    )
            except Exception as e:
                log.warning(f"Could not get terminal state for {session_id}: {e}")

    except Exception as e:
        log.error(f"Error sending terminal history to {sid}: {e}")


async def session_cleanup(sid, data):
    """Handle explicit session cleanup request."""
    try:
        session_id = data.get("sessionId")

        if not session_id:
            log.warning("Session cleanup request without sessionId")
            await sio_instance.emit(
                "cleanup_error", {"error": "sessionId required for cleanup"}, room=sid
            )
            return

        log.info(f"Session cleanup request for {session_id} from client {sid}")

        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
        
        # Close active terminal session
        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            try:
                await terminal.close()
                log.info(f"Closed active terminal session {session_id}")
            except Exception as e:
                log.error(f"Error closing terminal session {session_id}: {e}")

        # Clean up session buffers
        if session_id in AsyncioTerminal.session_buffers:
            del AsyncioTerminal.session_buffers[session_id]
            log.info(f"Cleaned up buffer for session {session_id}")

        # Clean up session ownership
        if session_id in AsyncioTerminal.session_owners:
            del AsyncioTerminal.session_owners[session_id]
            log.info(f"Cleaned up ownership for session {session_id}")

        await sio_instance.emit(
            "session_cleaned", {"success": True, "sessionId": session_id}, room=sid
        )

    except Exception as e:
        log.error(f"Error in session cleanup: {e}", exc_info=True)
        await sio_instance.emit("cleanup_error", {"error": str(e)}, room=sid)