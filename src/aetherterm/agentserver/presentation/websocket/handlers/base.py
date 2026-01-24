"""Base handlers and utilities for WebSocket operations."""

import logging
from aetherterm.agentserver.infrastructure.config import utils
from aetherterm.agentserver.infrastructure.config.utils import User

log = logging.getLogger("aetherterm.socket_handlers")

# Global storage for socket.io server instance
sio_instance = None
log_processing_manager = None


def socket_error_handler(error_event: str = "error"):
    """Decorator to handle socket operation errors consistently."""

    def decorator(func):
        async def wrapper(sid, data, *args, **kwargs):
            try:
                return await func(sid, data, *args, **kwargs)
            except Exception as e:
                log.error(f"Error in {func.__name__}: {e}", exc_info=True)
                await sio_instance.emit(error_event, {"error": str(e)}, room=sid)

        return wrapper

    return decorator


def set_sio_instance(sio):
    """Set the global socket.io server instance."""
    global sio_instance
    sio_instance = sio
    log.info("Socket.IO instance configured")


def get_user_info_from_environ(environ):
    """Extract user information from environment/headers."""

    user_info = {
        "remote_addr": environ.get("REMOTE_ADDR"),
        "remote_user": environ.get("HTTP_X_REMOTE_USER"),
        "user_agent": environ.get("HTTP_USER_AGENT"),
        "roles": [],
    }

    # Parse user information using the utils module
    user = User.create_from_environ(environ)
    user_info.update(user.get_user_context())

    return user_info


def check_session_ownership(session_id, current_user_info):
    """Check if user owns or can access a session."""
    from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
    
    if session_id not in AsyncioTerminal.session_owners:
        return True  # No owner set, allow access

    owner_info = AsyncioTerminal.session_owners[session_id]
    current_user = current_user_info.get("username")
    owner_user = owner_info.get("username")

    # Check if same user
    if current_user == owner_user:
        return True

    # Check if user has admin role
    if "admin" in current_user_info.get("roles", []):
        return True

    log.warning(
        f"Session access denied: {current_user} attempted to access session {session_id} owned by {owner_user}"
    )
    return False


def broadcast_to_session(session_id, message):
    """Broadcast a message to all clients connected to a specific session."""
    if not sio_instance:
        log.error("Socket.IO instance not available for broadcasting")
        return

    # Create a room name based on session_id
    room_name = f"session_{session_id}"

    # Emit to all clients in this session's room
    asyncio.create_task(
        sio_instance.emit("terminal_output", message, room=room_name)
    )
    log.debug(f"Broadcasted message to session {session_id}: {message}")