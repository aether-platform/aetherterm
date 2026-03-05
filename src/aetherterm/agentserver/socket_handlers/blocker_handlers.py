"""
Block/Unblock Socket.IO event handlers.
"""

import logging

from aetherterm.agentserver.auto_blocker import get_auto_blocker

from .helpers import get_sio

log = logging.getLogger("aetherterm.socket_handlers")


async def unblock_request(sid, data):
    """Handle unblock request from client."""
    sio = get_sio()
    try:
        session_id = data.get("session_id")
        unlock_key = data.get("unlock_key", "ctrl_d")

        if not session_id:
            log.warning("Unblock request without session_id")
            await sio.emit(
                "unblock_response", {"status": "error", "error": "session_id required"}, room=sid
            )
            return

        auto_blocker = get_auto_blocker()
        success = auto_blocker.unblock_session(session_id, unlock_key)

        if success:
            await sio.emit(
                "unblock_response",
                {
                    "status": "success",
                    "session_id": session_id,
                    "message": "Block has been released",
                },
                room=sid,
            )
            log.info(f"Session {session_id} unblocked by client {sid}")
        else:
            await sio.emit(
                "unblock_response",
                {
                    "status": "error",
                    "session_id": session_id,
                    "error": "Failed to unblock session",
                },
                room=sid,
            )

    except Exception as e:
        log.error(f"Error handling unblock request: {e}")
        await sio.emit("unblock_response", {"status": "error", "error": str(e)}, room=sid)


async def get_block_status(sid, data):
    """Handle block status request from client."""
    sio = get_sio()
    try:
        session_id = data.get("session_id")

        if not session_id:
            log.warning("Block status request without session_id")
            await sio.emit(
                "block_status_response",
                {"status": "error", "error": "session_id required"},
                room=sid,
            )
            return

        auto_blocker = get_auto_blocker()
        is_blocked = auto_blocker.is_session_blocked(session_id)
        block_state = auto_blocker.get_block_state(session_id)

        response_data = {"status": "success", "session_id": session_id, "is_blocked": is_blocked}

        if block_state:
            response_data.update(
                {
                    "reason": block_state.reason.value,
                    "message": block_state.message,
                    "alert_message": block_state.alert_message,
                    "detected_keywords": block_state.detected_keywords,
                    "blocked_at": block_state.blocked_at,
                }
            )

        await sio.emit("block_status_response", response_data, room=sid)

    except Exception as e:
        log.error(f"Error handling block status request: {e}")
        await sio.emit(
            "block_status_response", {"status": "error", "error": str(e)}, room=sid
        )
