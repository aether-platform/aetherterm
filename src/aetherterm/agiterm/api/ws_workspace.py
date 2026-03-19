"""Workspace-level WebSocket handler for multi-pane SDK sessions.

Protocol (JSON text frames only):

Server → Client:
  - {"type": "layout_sync", "layout": {...}}
  - {"type": "pane_added", "pane_id": "...", "role": "...", "tool": "...", "title": "..."}
  - {"type": "pane_removed", "pane_id": "..."}
  - {"type": "pane_output", "pane_id": "...", "data": "<base64>"}
  - {"type": "pane_status", "pane_id": "...", "status": "idle|busy|blocked"}
  - {"type": "pane_exited", "pane_id": "...", "exit_code": 0}
  - {"type": "pong"}

Client → Server:
  - {"type": "pane_input", "pane_id": "...", "data": "<base64>"}
  - {"type": "pane_resize", "pane_id": "...", "cols": 80, "rows": 24}
  - {"type": "pane_focus", "pane_id": "..."}
  - {"type": "ping"}
"""

import asyncio
import base64
import json
import logging
import os

from fastapi import WebSocket, WebSocketDisconnect

from aetherterm.agiterm.auth.api_key import APIKeyAuthenticator
from aetherterm.agiterm.sessions.manager import SDKSessionManager

log = logging.getLogger("agiterm.ws_workspace")


async def handle_workspace_websocket(
    websocket: WebSocket,
    session_id: str,
    auth: APIKeyAuthenticator,
    sessions: SDKSessionManager,
) -> None:
    """Handle a workspace-level WebSocket that multiplexes multiple panes.

    Authentication is done via query parameter: /ws/workspace/{session_id}?api_key=xxx
    """
    # Authenticate
    tenant = await auth.authenticate_websocket(websocket)

    # Verify the session exists and belongs to this tenant
    session = sessions.get_session(session_id, tenant.tenant_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    log.info(
        "Workspace WebSocket connected: session=%s tenant=%s user=%s",
        session_id,
        tenant.tenant_id,
        session.user_id,
    )

    # Track per-pane output tasks so we can cancel on disconnect
    pane_tasks: dict[str, asyncio.Task] = {}
    pane_queues: dict[str, asyncio.Queue[bytes]] = {}

    # Workspace event listener — receives events from add_pane/remove_pane
    async def on_workspace_event(event_type: str, data: dict) -> None:
        try:
            await websocket.send_text(json.dumps({"type": event_type, **data}))

            # Auto-start reader for newly added panes
            if event_type == "pane_added":
                pane_id = data.get("pane_id")
                if pane_id and pane_id not in pane_tasks:
                    pane = sessions.get_pane(session_id, tenant.tenant_id, pane_id)
                    if pane:
                        _start_pane_reader(
                            pane_id, pane.pty_session, websocket,
                            sessions, pane_tasks, pane_queues,
                        )
        except Exception:
            log.debug("Failed to send workspace event: %s", event_type)

    try:
        # Register listener for live updates from REST API
        session.add_workspace_listener(on_workspace_event)

        # Send initial layout sync
        layout = sessions.get_layout(session_id, tenant.tenant_id)
        if layout is not None:
            await websocket.send_text(
                json.dumps({"type": "layout_sync", "layout": layout})
            )

        # Start output readers for existing panes
        for pane in sessions.get_panes(session_id, tenant.tenant_id):
            _start_pane_reader(
                pane.pane_id,
                pane.pty_session,
                websocket,
                sessions,
                pane_tasks,
                pane_queues,
            )

        # Process incoming messages from client
        await _read_from_client(
            websocket, session_id, tenant.tenant_id, sessions, pane_tasks, pane_queues
        )

    except WebSocketDisconnect:
        log.info("Workspace WebSocket disconnected: session=%s", session_id)
    except Exception:
        log.exception("Workspace WebSocket error: session=%s", session_id)
    finally:
        session.remove_workspace_listener(on_workspace_event)
        # Cancel all pane output tasks
        for task in pane_tasks.values():
            task.cancel()
        # Remove queues from PTY clients
        for pane_id, queue in pane_queues.items():
            pane = sessions.get_pane(session_id, tenant.tenant_id, pane_id)
            if pane:
                pane.pty_session.clients.discard(queue)


def _start_pane_reader(
    pane_id: str,
    pty_session,
    websocket: WebSocket,
    sessions: SDKSessionManager,
    pane_tasks: dict[str, asyncio.Task],
    pane_queues: dict[str, asyncio.Queue[bytes]],
) -> None:
    """Start an asyncio task that reads PTY output for a pane and sends it over the WebSocket."""
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    pty_session.clients.add(queue)
    pane_queues[pane_id] = queue

    # Register the fd reader if not already registered (idempotent via manager)
    loop = asyncio.get_event_loop()
    try:
        loop.add_reader(
            pty_session.master_fd,
            sessions._on_pty_output,
            pty_session,
        )
    except Exception:
        # Reader may already be registered; that's fine
        pass

    async def _reader():
        try:
            while True:
                data = await queue.get()
                encoded = base64.b64encode(data).decode("ascii")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "pane_output",
                            "pane_id": pane_id,
                            "data": encoded,
                        }
                    )
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            log.debug("Pane reader stopped: pane=%s", pane_id)

    task = asyncio.create_task(_reader())
    pane_tasks[pane_id] = task


async def _read_from_client(
    websocket: WebSocket,
    session_id: str,
    tenant_id: str,
    sessions: SDKSessionManager,
    pane_tasks: dict[str, asyncio.Task],
    pane_queues: dict[str, asyncio.Queue[bytes]],
) -> None:
    """Read JSON messages from the workspace WebSocket client."""
    while True:
        raw = await websocket.receive_text()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")

        if msg_type == "ping":
            await websocket.send_text(json.dumps({"type": "pong"}))

        elif msg_type == "pane_input":
            pane_id = msg.get("pane_id")
            data_b64 = msg.get("data", "")
            if not pane_id:
                continue
            pane = sessions.get_pane(session_id, tenant_id, pane_id)
            if pane:
                try:
                    raw_bytes = base64.b64decode(data_b64)
                    pane.pty_session.write(raw_bytes)
                except Exception:
                    log.debug("Invalid base64 input for pane=%s", pane_id)

        elif msg_type == "pane_resize":
            pane_id = msg.get("pane_id")
            cols = msg.get("cols", 80)
            rows = msg.get("rows", 24)
            if not pane_id:
                continue
            pane = sessions.get_pane(session_id, tenant_id, pane_id)
            if pane:
                pane.pty_session.resize(cols, rows)

        elif msg_type == "pane_focus":
            # Informational — the server can use this for activity tracking.
            pane_id = msg.get("pane_id")
            if pane_id:
                log.debug("Focus changed to pane=%s session=%s", pane_id, session_id)
