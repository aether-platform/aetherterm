"""WebSocket handler for SDK terminal sessions.

Protocol:
  - Binary frames: raw PTY I/O (input from client, output from server)
  - Text frames: JSON control messages
    - {"type": "resize", "cols": 80, "rows": 24}
    - {"type": "ping"} → {"type": "pong"}
"""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.agiterm.sessions.manager import SDKSessionManager

log = logging.getLogger("agiterm.ws")


async def handle_sdk_websocket(
    websocket: WebSocket,
    session_id: str,
    auth: APIKeyAuthenticator,
    sessions: SDKSessionManager,
) -> None:
    """Handle a WebSocket connection for an SDK terminal session.

    Authentication is done via query parameter: /ws/sdk/{session_id}?api_key=xxx
    """
    # Authenticate
    tenant = await auth.authenticate_websocket(websocket)

    # Look up session
    session = sessions.get_session(session_id, tenant.tenant_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    log.info(
        "WebSocket connected: session=%s tenant=%s user=%s",
        session_id, tenant.tenant_id, session.user_id,
    )

    # Send scrollback history
    if session.pty_session.history:
        await websocket.send_bytes(bytes(session.pty_session.history))

    # Set up output streaming
    output_queue = await sessions.read_output(session)

    # Run input and output concurrently
    try:
        await asyncio.gather(
            _read_from_client(websocket, session, sessions),
            _write_to_client(websocket, output_queue),
        )
    except WebSocketDisconnect:
        log.info("WebSocket disconnected: session=%s", session_id)
    except Exception:
        log.exception("WebSocket error: session=%s", session_id)
    finally:
        session.pty_session.clients.discard(output_queue)


async def _read_from_client(
    websocket: WebSocket,
    session,
    sessions: SDKSessionManager,
) -> None:
    """Read input from WebSocket and write to PTY."""
    while True:
        message = await websocket.receive()

        if message.get("type") == "websocket.disconnect":
            break

        if "bytes" in message and message["bytes"]:
            # Binary frame: raw PTY input
            session.pty_session.write(message["bytes"])

        elif "text" in message and message["text"]:
            # Text frame: JSON control message
            try:
                msg = json.loads(message["text"])
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "resize":
                cols = msg.get("cols", 80)
                rows = msg.get("rows", 24)
                session.pty_session.resize(cols, rows)

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))


async def _write_to_client(
    websocket: WebSocket,
    output_queue: asyncio.Queue[bytes],
) -> None:
    """Read PTY output from queue and send to WebSocket."""
    while True:
        data = await output_queue.get()
        await websocket.send_bytes(data)
