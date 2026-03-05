"""InterAgentMessenger — WebSocket client for AI agents to communicate via AgentServer.

AI agents (Claude Code, CodeX, Gemini, etc.) running inside PTY panes use this
client to connect to AgentServer's /ws/agent/{agent_id} endpoint and exchange
messages with other pane agents through the MessageRouter.

Usage:
    messenger = InterAgentMessenger(agent_id="pane-0")
    await messenger.connect()  # connects to ws://localhost:57575/ws/agent/pane-0

    await messenger.send_dm("pane-1", "Hello from pane-0")
    await messenger.broadcast("Status update from pane-0")

    @messenger.on_message
    async def handle(msg):
        print(f"Received: {msg}")

    await messenger.disconnect()

Environment variables:
    AGENTSERVER_URL: WebSocket URL (default: ws://localhost:57575)
    AGENT_ID: Agent identifier, typically pane_id (auto-detected from PANE_ID if set)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import httpx

from .agent_protocol import AgentMessage, MessageBuilder, MessageType

log = logging.getLogger("aetherterm.agent_messenger")


class InterAgentMessenger:
    """WebSocket client for inter-agent communication through AgentServer."""

    def __init__(
        self,
        agent_id: str = "",
        server_url: str = "",
    ):
        self._agent_id = (
            agent_id
            or os.environ.get("AGENT_ID", "")
            or os.environ.get("PANE_ID", "")
            or "unknown"
        )
        self._server_url = (
            server_url
            or os.environ.get("AGENTSERVER_URL", "ws://localhost:57575")
        )
        self._ws = None
        self._message_handlers: List[Callable] = []
        self._recv_task: Optional[asyncio.Task] = None
        self._connected = False
        self._pending_requests: Dict[str, asyncio.Future] = {}

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to AgentServer WebSocket endpoint."""
        try:
            import websockets
        except ImportError:
            log.error("websockets package required: pip install websockets")
            return False

        url = f"{self._server_url}/ws/agent/{self._agent_id}"
        try:
            self._ws = await websockets.connect(url)
            self._connected = True
            self._recv_task = asyncio.create_task(self._receive_loop())
            log.info(f"Connected to AgentServer as {self._agent_id}: {url}")
            return True
        except Exception:
            log.exception(f"Failed to connect to {url}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from AgentServer."""
        self._connected = False
        if self._recv_task is not None:
            self._recv_task.cancel()
            self._recv_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        log.info(f"Disconnected: {self._agent_id}")

    async def send_dm(self, to_agent: str, content: str, summary: str = "") -> None:
        """Send a direct message to a specific agent (pane)."""
        msg = MessageBuilder.send_dm(self._agent_id, to_agent, content, summary)
        await self._send(msg)

    async def broadcast(self, content: str, summary: str = "") -> None:
        """Broadcast a message to all other agents."""
        msg = MessageBuilder.send_broadcast(self._agent_id, content, summary)
        await self._send(msg)

    async def signal_idle(self) -> None:
        """Signal that this agent is idle (triggers queued message delivery)."""
        msg = MessageBuilder.signal_idle(self._agent_id)
        await self._send(msg)

    async def signal_busy(self) -> None:
        """Signal that this agent is busy (messages will be queued)."""
        msg = MessageBuilder.signal_busy(self._agent_id)
        await self._send(msg)

    async def request_shutdown(self, target_agent: str, content: str = "") -> None:
        """Request another agent to shut down."""
        msg = MessageBuilder.request_shutdown(self._agent_id, target_agent, content)
        await self._send(msg)

    async def respond_shutdown(
        self, request_id: str, approve: bool, content: str = ""
    ) -> None:
        """Respond to a shutdown request."""
        msg = MessageBuilder.respond_shutdown(
            self._agent_id, "", request_id, approve, content
        )
        await self._send(msg)

    # --- Tmux control methods ---

    async def send_keys(self, pane_id: str, data: str, timeout: float = 5.0) -> Dict[str, Any]:
        """Send keystrokes to a specific pane."""
        return await self._tmux_request(
            {"type": "send_keys", "pane_id": pane_id, "data": data},
            timeout=timeout,
        )

    async def split_pane(
        self,
        session_id: str,
        direction: str = "v",
        cmd: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        role: str = "",
        window_id: str = "",
        target_pane_id: str = "",
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Split a pane, creating a new one with optional env and role."""
        payload: Dict[str, Any] = {
            "type": "split_pane",
            "session_id": session_id,
            "direction": direction,
            "role": role,
        }
        if cmd:
            payload["cmd"] = cmd
        if env:
            payload["env"] = env
        if window_id:
            payload["window_id"] = window_id
        if target_pane_id:
            payload["target_pane_id"] = target_pane_id
        return await self._tmux_request(payload, timeout=timeout)

    async def list_panes(self, session_id: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """List all panes in a session."""
        resp = await self._tmux_request(
            {"type": "list_panes", "session_id": session_id},
            timeout=timeout,
        )
        return resp.get("data", [])

    async def capture_pane(
        self, pane_id: str, lines: int = 100, timeout: float = 5.0
    ) -> str:
        """Capture a pane's scrollback history."""
        resp = await self._tmux_request(
            {"type": "capture_pane", "pane_id": pane_id, "lines": lines},
            timeout=timeout,
        )
        return resp.get("data", "")

    async def project_setup(
        self, spec: Dict[str, Any], timeout: float = 30.0
    ) -> Dict[str, Any]:
        """Create tmux windows/panes from a project spec via REST API.

        Args:
            spec: Project setup spec with session_name, windows, panes.
            timeout: HTTP request timeout in seconds.

        Returns:
            Dict with session_id, session_name, and windows list.
        """
        http_url = self._server_url.replace("ws://", "http://").replace(
            "wss://", "https://"
        )
        async with httpx.AsyncClient(
            base_url=http_url, timeout=timeout
        ) as client:
            resp = await client.post("/api/tmux/project-setup", json=spec)
            resp.raise_for_status()
            return resp.json()

    async def _tmux_request(
        self, payload: Dict[str, Any], timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Send a tmux command and wait for the response (request-response pattern)."""
        request_id = uuid4().hex[:12]
        payload["request_id"] = request_id

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = fut

        try:
            await self.send_raw(payload)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            log.warning(f"Tmux request {request_id} timed out")
            return {"success": False, "error": "timeout"}
        finally:
            self._pending_requests.pop(request_id, None)

    def on_message(self, callback: Callable) -> Callable:
        """Register a handler for incoming messages. Can be used as a decorator."""
        self._message_handlers.append(callback)
        return callback

    async def send_raw(self, data: Dict[str, Any]) -> None:
        """Send a raw JSON message (for custom message types)."""
        if self._ws is None or not self._connected:
            log.warning("Not connected, message dropped")
            return
        try:
            await self._ws.send(json.dumps(data))
        except Exception:
            log.exception("Failed to send raw message")

    async def _send(self, msg: AgentMessage) -> None:
        """Send an AgentMessage over WebSocket."""
        if self._ws is None or not self._connected:
            log.warning(f"Not connected, dropping {msg.message_type.value}")
            return
        try:
            await self._ws.send(json.dumps(msg.to_dict()))
        except Exception:
            log.exception(f"Failed to send {msg.message_type.value}")

    async def _receive_loop(self) -> None:
        """Background task receiving messages from AgentServer."""
        try:
            while self._connected and self._ws is not None:
                raw = await self._ws.recv()
                try:
                    data = json.loads(raw)

                    # Check if this is a response to a pending tmux request
                    if data.get("type") == "response" and "request_id" in data:
                        fut = self._pending_requests.get(data["request_id"])
                        if fut and not fut.done():
                            fut.set_result(data)
                        continue

                    msg = AgentMessage.from_dict(data)
                    await self._dispatch(msg)
                except (json.JSONDecodeError, KeyError, ValueError):
                    log.warning(f"Unparseable message: {str(raw)[:100]}")
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Receive loop error")
            self._connected = False

    async def _dispatch(self, msg: AgentMessage) -> None:
        """Dispatch incoming message to registered handlers."""
        for handler in self._message_handlers:
            try:
                result = handler(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("Message handler error")
