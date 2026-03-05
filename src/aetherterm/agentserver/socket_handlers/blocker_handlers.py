"""
Block/Unblock Socket.IO event handlers.

薄いアダプター層として、BlockerUseCases に処理を委譲します。
"""

import logging

from dependency_injector.wiring import Provide, inject

from aetherterm.agentserver.containers import ApplicationContainer

from .helpers import get_sio

log = logging.getLogger("aetherterm.socket_handlers")


@inject
async def unblock_request(
    sid,
    data,
    blocker_use_cases=Provide[ApplicationContainer.blocker_use_cases],
):
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

        success = await blocker_use_cases.unblock_session(session_id, unlock_key)

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


@inject
async def get_block_status(
    sid,
    data,
    blocker_use_cases=Provide[ApplicationContainer.blocker_use_cases],
):
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

        is_blocked = blocker_use_cases.is_session_blocked(session_id)
        block_state = blocker_use_cases.get_block_state(session_id)

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
