"""WebSocket handler for tmux multiplexer.

Single WebSocket per session. Binary frames for PTY I/O, text frames for control.
Binary frame format: [1 byte: pane_id_len][N bytes: pane_id][M bytes: pty_data]
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from aetherterm.common.agent_protocol import AgentMessage, MessageType
from aetherterm.core.ws.framing import decode_binary_frame, encode_binary_frame

from .session_registry import TmuxSessionRegistry
from .status_bar import generate_status

if TYPE_CHECKING:
    from ...core.messaging.message_router import MessageRouter

log = logging.getLogger("aetherterm.tmux.ws")


class TmuxWebSocketHandler:
    """Handles a single WebSocket client for a tmux session."""

    def __init__(
        self,
        registry: TmuxSessionRegistry,
        message_router: Optional[MessageRouter] = None,
    ):
        self.registry = registry
        self.message_router = message_router

    async def handle(self, websocket: WebSocket, session_id: str) -> None:
        """Main WebSocket handler for /ws/tmux/{session_id}."""
        await websocket.accept()

        # Create or attach to session
        create_new = session_id == "_new"
        if create_new:
            session = self.registry.create_session()
            window = await self.registry.create_window(session.session_id)
            if window is None:
                await websocket.close(code=1011, reason="Failed to create window")
                return
            session_id = session.session_id
        else:
            session = self.registry.get_session(session_id)
            if session is None:
                # Auto-create if doesn't exist
                session = self.registry.create_session(session_id=session_id)
                window = await self.registry.create_window(session.session_id)
                if window is None:
                    await websocket.close(code=1011, reason="Failed to create window")
                    return

        # Register client queue for control messages
        control_queue: asyncio.Queue = asyncio.Queue()
        session.client_queues.add(control_queue)

        # Register state change callback
        async def on_state_change(sid: str, event: Dict[str, Any]) -> None:
            if sid == session_id:
                with contextlib.suppress(asyncio.QueueFull):
                    control_queue.put_nowait(("state_update", event))

        self.registry.on_state_change(on_state_change)

        # Collect per-pane read queues
        pane_queues: Dict[str, asyncio.Queue] = {}

        # Register all existing panes as agents in MessageRouter
        registered_pane_ids: list[str] = []
        if self.message_router is not None:
            for window in session.windows.values():
                for pane_id in window.panes:
                    await self._register_pane_agent(
                        pane_id, websocket, control_queue
                    )
                    registered_pane_ids.append(pane_id)

        try:
            # Send initial state
            await self._send_state_sync(websocket, session)

            # Set up pane output readers for all current panes
            await self._sync_pane_queues(session, pane_queues)

            # Main loop: read from client + write to client
            await asyncio.gather(
                self._read_from_client(websocket, session_id),
                self._write_to_client(websocket, session_id, control_queue, pane_queues),
            )
        except WebSocketDisconnect:
            log.info(f"Client disconnected from session {session_id}")
        except Exception:
            log.exception(f"WebSocket error for session {session_id}")
        finally:
            session = self.registry.get_session(session_id)
            if session is not None:
                session.client_queues.discard(control_queue)
                # Remove pane queues
                for pane_id, q in pane_queues.items():
                    loc = self.registry.find_pane_location(pane_id)
                    if loc is not None:
                        pane = self.registry._get_pane(loc[0], loc[1], pane_id)
                        if pane is not None:
                            pane.clients.discard(q)

            # Unregister pane agents from MessageRouter
            if self.message_router is not None:
                for pane_id in registered_pane_ids:
                    await self.message_router.unregister_agent(pane_id)

            # Remove callback
            if on_state_change in self.registry._state_callbacks:
                self.registry._state_callbacks.remove(on_state_change)

    async def _send_state_sync(self, websocket: WebSocket, session: Any) -> None:
        """Send full session state to client."""
        msg = json.dumps(
            {
                "type": "state_sync",
                "session": session.to_dict(),
            }
        )
        await websocket.send_text(msg)

        # Send history for all panes
        for window in session.windows.values():
            for pane_id, pane in window.panes.items():
                if pane.history:
                    frame = encode_binary_frame(pane_id, bytes(pane.history))
                    await websocket.send_bytes(frame)

    async def _sync_pane_queues(
        self,
        session: Any,
        pane_queues: Dict[str, asyncio.Queue],
    ) -> None:
        """Set up output queues for all panes in the session."""
        for window in session.windows.values():
            for pane_id, pane in window.panes.items():
                if pane_id not in pane_queues:
                    q: asyncio.Queue = asyncio.Queue()
                    pane.clients.add(q)
                    pane_queues[pane_id] = q

    async def _read_from_client(self, websocket: WebSocket, session_id: str) -> None:
        """Read messages from the WebSocket client."""
        while True:
            msg = await websocket.receive()

            if "bytes" in msg:
                # Binary frame: PTY input
                pane_id, data = decode_binary_frame(msg["bytes"])
                if pane_id and data:
                    loc = self.registry.find_pane_location(pane_id)
                    if loc is not None:
                        self.registry.write_to_pane(loc[0], loc[1], pane_id, data)

            elif "text" in msg:
                try:
                    cmd = json.loads(msg["text"])
                    await self._handle_control_message(websocket, session_id, cmd)
                except json.JSONDecodeError:
                    log.warning(f"Invalid JSON from client: {msg['text'][:100]}")

    async def _write_to_client(
        self,
        websocket: WebSocket,
        session_id: str,
        control_queue: asyncio.Queue,
        pane_queues: Dict[str, asyncio.Queue],
    ) -> None:
        """Write PTY output and control messages to the WebSocket client."""

        async def write_control():
            while True:
                msg = await control_queue.get()
                if msg is None:
                    break
                msg_type, data = msg
                await websocket.send_text(json.dumps({"type": msg_type, **data}))

                # If new panes were created, sync queues
                session = self.registry.get_session(session_id)
                if session is not None:
                    await self._sync_pane_queues(session, pane_queues)

        async def write_pane_output(pane_id: str, queue: asyncio.Queue):
            try:
                while True:
                    data = await queue.get()
                    if data is None:
                        # Pane exited
                        break
                    frame = encode_binary_frame(pane_id, data)
                    await websocket.send_bytes(frame)
            except Exception:
                pass

        # Start output readers for existing panes
        tasks = [asyncio.create_task(write_control())]
        started_panes = set()

        while True:
            # Start tasks for any new panes
            for pane_id, queue in list(pane_queues.items()):
                if pane_id not in started_panes:
                    tasks.append(asyncio.create_task(write_pane_output(pane_id, queue)))
                    started_panes.add(pane_id)

            # Wait for any task to complete
            done, pending = await asyncio.wait(
                tasks, timeout=0.5, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                tasks.remove(task)
                # Re-check for errors
                if task.exception():
                    raise task.exception()

            if not tasks and not pane_queues:
                break

    async def _handle_control_message(
        self,
        websocket: WebSocket,
        session_id: str,
        msg: Dict[str, Any],
    ) -> None:
        """Handle a JSON control message from the client."""
        msg_type = msg.get("type", "")

        if msg_type == "session_create":
            session = self.registry.create_session(name=msg.get("name", ""))
            window = await self.registry.create_window(session.session_id)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "state_sync",
                        "session": session.to_dict(),
                    }
                )
            )

        elif msg_type == "session_attach":
            target_id = msg.get("session_id", "")
            session = self.registry.get_session(target_id)
            if session is not None:
                await self._send_state_sync(websocket, session)

        elif msg_type == "session_detach":
            # Client will close the WebSocket
            await websocket.close(code=1000, reason="Detached")

        elif msg_type == "session_list":
            sessions = self.registry.list_sessions()
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "session_list",
                        "sessions": sessions,
                    }
                )
            )

        elif msg_type == "window_create":
            window = await self.registry.create_window(
                session_id,
                name=msg.get("name", ""),
                cmd=msg.get("cmd"),
            )
            if window is not None:
                self.registry.select_window(session_id, window.window_id)
                session = self.registry.get_session(session_id)
                if session:
                    await self._send_state_sync(websocket, session)

        elif msg_type == "window_close":
            await self.registry.close_window(session_id, msg["window_id"])
            session = self.registry.get_session(session_id)
            if session:
                await self._send_state_sync(websocket, session)

        elif msg_type == "window_select":
            self.registry.select_window(session_id, msg["window_id"])
            session = self.registry.get_session(session_id)
            if session:
                await self._send_state_sync(websocket, session)

        elif msg_type == "window_rename":
            session = self.registry.get_session(session_id)
            if session:
                window = session.windows.get(msg.get("window_id", ""))
                if window:
                    window.name = msg.get("name", window.name)

        elif msg_type == "session_rename":
            session = self.registry.get_session(session_id)
            if session:
                session.name = msg.get("name", session.name)

        elif msg_type == "pane_split":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                new_pane = await self.registry.split_pane(
                    session_id,
                    window_id,
                    target_pane_id=msg.get("pane_id", ""),
                    direction=msg.get("direction", "v"),
                    cmd=msg.get("cmd"),
                )
                if new_pane:
                    await self._send_state_sync(websocket, session)

        elif msg_type == "pane_close":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                await self.registry.close_pane(session_id, window_id, msg["pane_id"])
                session = self.registry.get_session(session_id)
                if session:
                    await self._send_state_sync(websocket, session)

        elif msg_type == "pane_focus":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                self.registry.focus_pane(session_id, window_id, msg["pane_id"])

        elif msg_type == "pane_resize_pty":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                self.registry.resize_pane_pty(
                    session_id,
                    window_id,
                    msg["pane_id"],
                    cols=msg["cols"],
                    rows=msg["rows"],
                )

        elif msg_type == "layout_resize":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                self.registry.resize_layout(
                    session_id,
                    window_id,
                    msg["pane_id"],
                    msg.get("delta", 0.05),
                )
                window = session.windows.get(window_id)
                if window:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "state_update",
                                "layout": window.layout.to_dict(),
                                "window_id": window_id,
                            }
                        )
                    )

        elif msg_type == "layout_preset":
            session = self.registry.get_session(session_id)
            if session:
                window_id = msg.get("window_id", session.active_window_id)
                await self.registry.apply_preset_layout(
                    session_id,
                    window_id,
                    msg["preset"],
                )
                await self._send_state_sync(websocket, session)

        elif msg_type == "status_request":
            session = self.registry.get_session(session_id)
            if session:
                status = generate_status(session)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "status_update",
                            **status,
                        }
                    )
                )

        elif msg_type == "pane_input":
            # JSON-based input (alternative to binary frames)
            pane_id = msg.get("pane_id", "")
            data = msg.get("data", "").encode("utf-8")
            if pane_id and data:
                loc = self.registry.find_pane_location(pane_id)
                if loc:
                    self.registry.write_to_pane(loc[0], loc[1], pane_id, data)

        elif msg_type == "resize":
            # Legacy resize for a specific pane
            pane_id = msg.get("pane_id", "")
            if pane_id:
                loc = self.registry.find_pane_location(pane_id)
                if loc:
                    self.registry.resize_pane_pty(
                        loc[0],
                        loc[1],
                        pane_id,
                        cols=msg["cols"],
                        rows=msg["rows"],
                    )

        # --- Inter-Agent Messaging ---

        elif msg_type in ("agent_dm", "agent_broadcast"):
            if self.message_router is not None:
                agent_msg = AgentMessage.from_dict(msg) if "message_id" in msg else \
                    AgentMessage(
                        from_agent=msg.get("from_agent", ""),
                        to_agent=msg.get("to_agent", ""),
                        message_type=MessageType.AGENT_DM if msg_type == "agent_dm" else MessageType.AGENT_BROADCAST,
                        payload=msg.get("payload", {}),
                    )
                await self.message_router.route_message(agent_msg)

        elif msg_type == "agent_idle":
            if self.message_router is not None:
                pane_id = msg.get("pane_id", msg.get("agent_id", ""))
                if pane_id:
                    await self.message_router.set_agent_idle(pane_id)

        elif msg_type == "agent_busy":
            if self.message_router is not None:
                pane_id = msg.get("pane_id", msg.get("agent_id", ""))
                if pane_id:
                    await self.message_router.set_agent_busy(pane_id)

        elif msg_type in ("shutdown_request", "shutdown_response"):
            if self.message_router is not None:
                mt = MessageType.SHUTDOWN_REQUEST if msg_type == "shutdown_request" else MessageType.SHUTDOWN_RESPONSE
                agent_msg = AgentMessage(
                    from_agent=msg.get("from_agent", ""),
                    to_agent=msg.get("to_agent", ""),
                    message_type=mt,
                    payload=msg.get("payload", {}),
                )
                await self.message_router.route_message(agent_msg)

    async def _register_pane_agent(
        self,
        pane_id: str,
        websocket: WebSocket,
        control_queue: asyncio.Queue,
    ) -> None:
        """Register a pane as an agent in the MessageRouter."""
        if self.message_router is None:
            return

        async def ws_deliver(agent_msg: AgentMessage) -> None:
            """Deliver agent message to browser client via control queue."""
            with contextlib.suppress(asyncio.QueueFull):
                control_queue.put_nowait((
                    "agent_message",
                    {
                        "pane_id": pane_id,
                        **agent_msg.to_dict(),
                    },
                ))

        await self.message_router.register_agent(
            pane_id, ws_send_callback=ws_deliver
        )
