"""Terminal operation handlers."""

import logging
from .base import sio_instance, socket_error_handler, check_session_ownership, get_user_info_from_environ
from ..terminal_creation_service import create_terminal_with_service

log = logging.getLogger("aetherterm.socket_handlers")


async def create_terminal(
    sid,
    data,
    config_login: bool = False,
    config_pam_profile: str = "",
    config_uri_root_path: str = "",
):
    """Handle the creation of a new terminal session with optional agent configuration."""
    # Use the refactored service for terminal creation
    await create_terminal_with_service(
        sid=sid,
        data=data,
        sio_instance=sio_instance,
        config_login=config_login,
        config_pam_profile=config_pam_profile,
        config_uri_root_path=config_uri_root_path,
    )


async def resume_terminal(sid, data):
    """Handle resuming an existing terminal session or create new if not found."""
    try:
        session_id = data.get("sessionId")
        tab_id = data.get("tabId")
        sub_type = data.get("subType")
        cols = data.get("cols", 80)
        rows = data.get("rows", 24)

        log.info(f"Resume terminal request for session {session_id} from client {sid}")
        
        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
        
        log.info(f"Available sessions: {list(AsyncioTerminal.sessions.keys())}")
        log.info(f"Session buffers available: {list(AsyncioTerminal.session_buffers.keys())}")

        if not session_id:
            log.warning("Resume terminal request without sessionId")
            await sio_instance.emit(
                "terminal_error", {"error": "sessionId required for resume"}, room=sid
            )
            return

        # Check if session exists and is active
        if session_id in AsyncioTerminal.sessions:
            existing_terminal = AsyncioTerminal.sessions[session_id]
            if not existing_terminal.closed:
                log.info(f"Resuming existing active terminal session {session_id}")

                # Add this client to the existing terminal's client set
                existing_terminal.client_sids.add(sid)

                # Send terminal history/buffer content first
                from .connection import send_terminal_history
                await send_terminal_history(sid, session_id, existing_terminal)

                # Then notify client that terminal is ready (resumed)
                await sio_instance.emit(
                    "terminal_ready",
                    {
                        "session": session_id,
                        "status": "resumed",
                        "tabId": tab_id,
                        "subType": sub_type,
                    },
                    room=sid,
                )
                log.info(f"Terminal session {session_id} successfully resumed for client {sid}")
                return
            log.info(f"Session {session_id} exists but is closed, will create new terminal")
        else:
            log.info(f"Session {session_id} not found, will create new terminal")

        # Session doesn't exist or is closed - create new terminal with the provided session ID
        log.info(f"Creating new terminal session with ID {session_id}")

        # Use create_terminal to create new session with specified session_id
        await create_terminal(
            sid,
            {
                "session": session_id,
                "tabId": tab_id,
                "subType": sub_type,
                "cols": cols,
                "rows": rows,
                "user": "",
                "path": "",
            },
        )

    except Exception as e:
        log.error(f"Error resuming terminal: {e}", exc_info=True)
        await sio_instance.emit("terminal_error", {"error": str(e)}, room=sid)


async def get_session_info(sid, data):
    """Get information about a session for debugging."""
    try:
        session_id = data.get("session")
        if not session_id:
            await sio_instance.emit("session_info", {"error": "No session ID provided"}, room=sid)
            return

        from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
        
        info = {
            "sessionId": session_id,
            "exists": False,
            "active": False,
            "clientCount": 0,
            "history": False,
            "historyLength": 0,
        }

        # Check if session exists in AsyncioTerminal sessions
        if session_id in AsyncioTerminal.sessions:
            terminal = AsyncioTerminal.sessions[session_id]
            info["exists"] = True
            info["active"] = not terminal.closed
            info["clientCount"] = len(terminal.client_sids) if hasattr(terminal, 'client_sids') else 0

        # Check if session has history/buffer
        if session_id in AsyncioTerminal.session_buffers:
            info["history"] = True
            info["historyLength"] = len(AsyncioTerminal.session_buffers[session_id])

        await sio_instance.emit("session_info", info, room=sid)

    except Exception as e:
        log.error(f"Error getting session info: {e}", exc_info=True)
        await sio_instance.emit("session_info", {"error": str(e)}, room=sid)


@socket_error_handler("terminal_error")
async def terminal_input(sid, data):
    """Handle terminal input from client."""
    session_id = data.get("session")
    input_data = data.get("data")

    if not session_id or input_data is None:
        log.warning("Terminal input request missing session or data")
        return

    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    # Check if session exists
    if session_id not in AsyncioTerminal.sessions:
        log.error(f"Terminal input for non-existent session: {session_id}")
        await sio_instance.emit(
            "terminal_error", {"error": f"Session {session_id} not found"}, room=sid
        )
        return

    terminal = AsyncioTerminal.sessions[session_id]

    # Security check: Verify session ownership
    user_info = get_user_info_from_environ(data.get("environ", {}))
    if not check_session_ownership(session_id, user_info):
        await sio_instance.emit(
            "terminal_error", {"error": "Access denied to session"}, room=sid
        )
        return

    try:
        await terminal.write(input_data)
        log.debug(f"Sent input to terminal {session_id}: {repr(input_data)}")
    except Exception as e:
        log.error(f"Error sending input to terminal {session_id}: {e}")
        await sio_instance.emit(
            "terminal_error", {"error": f"Failed to send input: {str(e)}"}, room=sid
        )


@socket_error_handler("terminal_error")
async def terminal_resize(sid, data):
    """Handle terminal resize requests."""
    session_id = data.get("session")
    cols = data.get("cols")
    rows = data.get("rows")

    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    if session_id in AsyncioTerminal.sessions:
        terminal = AsyncioTerminal.sessions[session_id]
        await terminal.resize(cols, rows)
        log.info(f"Resized terminal {session_id} to {cols}x{rows}")
    else:
        log.warning(f"Resize request for non-existent session: {session_id}")