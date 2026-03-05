import asyncio
import contextlib
import json
import logging
from typing import Any, Dict

from aetherterm.common.agent_protocol import AgentMessage, MessageType

log = logging.getLogger("aetherterm.handlers")


class ControlCommandHandler:
    """Handles inbound control commands from ControlServer."""

    def __init__(self, tmux_registry: Any):
        self.tmux_registry = tmux_registry

    async def handle_command(self, command_type: str, payload: Dict[str, Any]) -> None:
        """Execute inbound control commands."""
        if command_type == "emergency_stop":
            log.warning(f"EMERGENCY STOP received: {payload}")
            for sid in list(self.tmux_registry.sessions.keys()):
                await self.tmux_registry.destroy_session(sid)

        elif command_type == "kill_session":
            session_id = payload.get("session_id", "")
            log.warning(f"Killing session: {session_id}")
            await self.tmux_registry.destroy_session(session_id)

        elif command_type == "block_input":
            await self._set_input_blocked(payload, True)

        elif command_type == "unblock_input":
            await self._set_input_blocked(payload, False)

        elif command_type == "shell_command":
            await self._route_shell_command(payload)

        elif command_type == "registration_confirmed":
            log.info(f"Registration confirmed by ControlServer: {payload}")

        else:
            log.debug(f"Unhandled control command: {command_type}")

    async def _set_input_blocked(self, payload: Dict[str, Any], blocked: bool) -> None:
        session_id = payload.get("session_id", "")
        pane_id = payload.get("pane_id", "")
        reason = payload.get("reason", "Action by ControlServer")

        log.info(
            f"{'Blocking' if blocked else 'Unblocking'} input: session={session_id} pane={pane_id}"
        )

        if pane_id:
            loc = self.tmux_registry.find_pane_location(pane_id)
            if loc:
                self.tmux_registry.set_pane_blocked(loc[0], loc[1], pane_id, blocked)
        elif session_id:
            session = self.tmux_registry.get_session(session_id)
            if session:
                for window in session.windows.values():
                    for pid in window.panes:
                        self.tmux_registry.set_pane_blocked(
                            session_id, window.window_id, pid, blocked
                        )

        event_type = "input_blocked" if blocked else "input_unblocked"
        await self._notify_clients(
            session_id,
            {
                "type": event_type,
                "session_id": session_id,
                "pane_id": pane_id,
                "reason": reason if blocked else None,
            },
        )

    async def _route_shell_command(self, payload: Dict[str, Any]) -> None:
        """Route a command from ControlServer to a specific pane (AgentShell target).

        The ControlServer sends shell_command with target_shell_id. Since
        AgentShell instances are PTY child processes managed by this AgentServer,
        we find the corresponding pane and write the command to its PTY.
        """
        target_shell_id = payload.get("target_shell_id", "")
        command = payload.get("command", "")
        session_id = payload.get("session_id", "")
        pane_id = payload.get("pane_id", "")

        if not command:
            log.warning("shell_command received with empty command")
            return

        # If pane_id is provided directly, use it
        if pane_id:
            loc = self.tmux_registry.find_pane_location(pane_id)
            if loc:
                data = command.encode("utf-8") if isinstance(command, str) else command
                self.tmux_registry.write_to_pane(loc[0], loc[1], pane_id, data)
                log.info(f"Shell command routed to pane {pane_id}")
                return

        # Otherwise, try to find pane by session_id (write to active pane)
        if session_id:
            session = self.tmux_registry.get_session(session_id)
            if session and session.active_window_id:
                window = session.windows.get(session.active_window_id)
                if window and window.active_pane_id:
                    data = command.encode("utf-8") if isinstance(command, str) else command
                    self.tmux_registry.write_to_pane(
                        session_id, window.window_id, window.active_pane_id, data
                    )
                    log.info(
                        f"Shell command routed to active pane "
                        f"{window.active_pane_id} (target_shell={target_shell_id})"
                    )
                    return

        log.warning(
            f"Could not route shell_command: target_shell={target_shell_id} "
            f"session={session_id} pane={pane_id}"
        )

    async def _notify_clients(self, session_id: str, event: dict) -> None:
        session = self.tmux_registry.get_session(session_id)
        if session is None:
            return
        for q in session.client_queues:
            try:
                q.put_nowait(("state_update", event))
            except asyncio.QueueFull:
                pass


async def handle_agent_websocket(
    websocket: Any,
    agent_id: str,
    message_router: Any,
    agent_manager: Any,
    tmux_registry: Any = None,
):
    """WebSocket endpoint for external AI agents (Claude Code, CodeX, Gemini, etc.).

    AI agents running in PTY panes connect here to send/receive inter-agent
    messages via the MessageRouter, and to control tmux panes (send-keys,
    split-window, list-panes, capture-pane).

    Protocol (JSON text frames):
      → {"message_type": "agent_dm", "from_agent": "...", "to_agent": "...", ...}
      → {"message_type": "agent_broadcast", "from_agent": "...", ...}
      → {"message_type": "agent_idle", ...}
      → {"message_type": "agent_busy", ...}
      → {"type": "send_keys", "pane_id": "...", "data": "...", "request_id": "..."}
      → {"type": "split_pane", "session_id": "...", "direction": "v", ...}
      → {"type": "list_panes", "session_id": "...", ...}
      → {"type": "capture_pane", "pane_id": "...", "lines": 100, ...}
      ← {"message_type": "agent_dm", "from_agent": "...", "payload": {...}, ...}
      ← {"type": "response", "request_id": "...", "success": true, "data": ...}
    """
    await websocket.accept()
    log.info(f"Agent {agent_id} connected via /ws/agent/")

    async def ws_deliver(agent_msg: AgentMessage) -> None:
        with contextlib.suppress(Exception):
            await websocket.send_json(agent_msg.to_dict())

    async def ws_respond(request_id: str, success: bool, data: Any = None, error: str = "") -> None:
        """Send a response frame for request-response tmux commands."""
        resp: Dict[str, Any] = {
            "type": "response",
            "request_id": request_id,
            "success": success,
        }
        if data is not None:
            resp["data"] = data
        if error:
            resp["error"] = error
        with contextlib.suppress(Exception):
            await websocket.send_json(resp)

    await message_router.register_agent(agent_id, ws_send_callback=ws_deliver)

    try:
        while True:
            data = await websocket.receive()
            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                    msg_type = msg.get("message_type", msg.get("type", ""))

                    if msg_type in (
                        MessageType.AGENT_DM.value,
                        MessageType.AGENT_BROADCAST.value,
                        MessageType.SHUTDOWN_REQUEST.value,
                        MessageType.SHUTDOWN_RESPONSE.value,
                    ):
                        agent_msg = AgentMessage.from_dict(msg)
                        await message_router.route_message(agent_msg)
                    elif msg_type == MessageType.AGENT_IDLE.value:
                        await message_router.set_agent_idle(agent_id)
                    elif msg_type == MessageType.AGENT_BUSY.value:
                        await message_router.set_agent_busy(agent_id)

                    # --- Tmux control commands ---
                    elif msg_type == "send_keys" and tmux_registry:
                        await _handle_send_keys(msg, tmux_registry, ws_respond)
                    elif msg_type == "split_pane" and tmux_registry:
                        await _handle_split_pane(msg, tmux_registry, ws_respond)
                    elif msg_type == "list_panes" and tmux_registry:
                        await _handle_list_panes(msg, tmux_registry, ws_respond)
                    elif msg_type == "capture_pane" and tmux_registry:
                        await _handle_capture_pane(msg, tmux_registry, ws_respond)

                    else:
                        await agent_manager.handle_agent_message(
                            agent_id, msg, send_callback=ws_deliver
                        )
                except json.JSONDecodeError:
                    log.warning(f"Invalid JSON from agent {agent_id}")
    except Exception:
        pass
    finally:
        await message_router.unregister_agent(agent_id)
        log.info(f"Agent {agent_id} disconnected")


# --- Tmux control command handlers ---


async def _handle_send_keys(
    msg: Dict[str, Any], registry: Any, respond: Any
) -> None:
    """Send keystrokes to a specific pane."""
    request_id = msg.get("request_id", "")
    pane_id = msg.get("pane_id", "")
    keys_data = msg.get("data", "")

    if not pane_id or not keys_data:
        await respond(request_id, False, error="pane_id and data required")
        return

    loc = registry.find_pane_location(pane_id)
    if loc is None:
        await respond(request_id, False, error=f"pane {pane_id} not found")
        return

    data_bytes = keys_data.encode("utf-8") if isinstance(keys_data, str) else keys_data
    ok = registry.write_to_pane(loc[0], loc[1], pane_id, data_bytes)
    await respond(request_id, ok, error="" if ok else "write failed (pane blocked or closed)")


async def _handle_split_pane(
    msg: Dict[str, Any], registry: Any, respond: Any
) -> None:
    """Split a pane, creating a new one with optional env and role."""
    request_id = msg.get("request_id", "")
    session_id = msg.get("session_id", "")
    direction = msg.get("direction", "v")
    cmd = msg.get("cmd")
    env = msg.get("env")
    role = msg.get("role", "")

    if not session_id:
        await respond(request_id, False, error="session_id required")
        return

    session = registry.get_session(session_id)
    if session is None:
        await respond(request_id, False, error=f"session {session_id} not found")
        return

    window_id = msg.get("window_id", session.active_window_id)
    target_pane_id = msg.get("target_pane_id", "")

    new_pane = await registry.split_pane(
        session_id, window_id,
        target_pane_id=target_pane_id,
        direction=direction,
        cmd=cmd, env=env, role=role,
    )
    if new_pane is None:
        await respond(request_id, False, error="split failed")
        return

    await respond(request_id, True, data=new_pane.to_dict())


async def _handle_list_panes(
    msg: Dict[str, Any], registry: Any, respond: Any
) -> None:
    """List all panes in a session."""
    request_id = msg.get("request_id", "")
    session_id = msg.get("session_id", "")

    if not session_id:
        await respond(request_id, False, error="session_id required")
        return

    session = registry.get_session(session_id)
    if session is None:
        await respond(request_id, False, error=f"session {session_id} not found")
        return

    panes = []
    for window in session.windows.values():
        for pane in window.panes.values():
            pane_dict = pane.to_dict()
            pane_dict["window_id"] = window.window_id
            pane_dict["window_name"] = window.name
            panes.append(pane_dict)

    await respond(request_id, True, data=panes)


async def _handle_capture_pane(
    msg: Dict[str, Any], registry: Any, respond: Any
) -> None:
    """Capture a pane's scrollback history."""
    request_id = msg.get("request_id", "")
    pane_id = msg.get("pane_id", "")
    max_lines = msg.get("lines", 100)

    if not pane_id:
        await respond(request_id, False, error="pane_id required")
        return

    loc = registry.find_pane_location(pane_id)
    if loc is None:
        await respond(request_id, False, error=f"pane {pane_id} not found")
        return

    session = registry.get_session(loc[0])
    window = session.windows.get(loc[1])
    pane = window.panes.get(pane_id)

    # Decode history, take last N lines
    try:
        text = pane.history.decode("utf-8", errors="replace")
    except Exception:
        text = pane.history.decode("latin-1")

    lines = text.splitlines()
    if max_lines > 0:
        lines = lines[-max_lines:]

    await respond(request_id, True, data="\n".join(lines))
