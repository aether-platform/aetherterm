"""NATS Bridge — enables NATS messaging for AgentShell.

Adds NATS pub/sub capabilities to TerminalPTY or PTYChain:
- Subscribes to agent.{id}.inbox for receiving DMs/tasks
- Injects received messages into PTY as commands
- Publishes shell output snippets to NATS for monitoring
- Sends heartbeat and status updates

Supports two PTY backends:
- PTYChain: uses inject_command(str) and set_on_shell_output(callback)
- TerminalPTY: uses send_input(bytes) and add_event_callback(callback)

Usage:
    bridge = NATSBridge(agent_id="coder-1", role="coder")
    await bridge.start(terminal_pty)  # Attach to TerminalPTY or PTYChain
    # ... PTY runs ...
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Ring buffer size for output tracking
_OUTPUT_RING_SIZE = 4096


class NATSBridge:
    """NATS messaging bridge for TerminalPTY / PTYChain.

    Attaches to an existing PTY instance and provides:
    - NATS inbox subscription → inject commands into PTY
    - Shell output monitoring → NATS publish for timeline
    - Agent registration, heartbeat, status
    """

    def __init__(
        self,
        agent_id: str,
        role: str = "shell",
        nats_url: str | None = None,
    ):
        self.agent_id = agent_id
        self.role = role
        self.nats_url = nats_url or os.environ.get("NATS_URL", "nats://localhost:4222")
        self._nc = None  # nats client
        self._pty = None
        self._pty_mode = None  # "pty_chain" or "terminal_pty"
        self._running = False
        self._output_ring = bytearray()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start(self, pty) -> None:
        """Attach to a PTY instance and start NATS bridge.

        Args:
            pty: PTYChain (has inject_command/set_on_shell_output) or
                 TerminalPTY (has send_input/add_event_callback)
        """
        self._pty = pty
        self._running = True

        # Detect PTY type and register output callback
        if hasattr(pty, "inject_command") and hasattr(pty, "set_on_shell_output"):
            self._pty_mode = "pty_chain"
            pty.set_on_shell_output(self._on_shell_output)
        elif hasattr(pty, "send_input") and hasattr(pty, "add_event_callback"):
            self._pty_mode = "terminal_pty"
            pty.add_event_callback(self._on_terminal_event)
        else:
            logger.warning("Unknown PTY type: %s", type(pty).__name__)

        # Connect to NATS
        try:
            import nats as nats_lib

            self._nc = await nats_lib.connect(
                servers=self.nats_url,
                max_reconnect_attempts=5,
                reconnect_time_wait=2,
                name=f"agentshell-{self.agent_id}",
            )
            logger.info("NATS bridge connected: %s (agent=%s)", self.nats_url, self.agent_id)

            # Register with discovery
            await self._publish_registration()

            # Subscribe to inbox + broadcast
            await self._nc.subscribe(
                f"agent.{self.agent_id}.inbox", cb=self._on_nats_message
            )
            await self._nc.subscribe("agent.broadcast", cb=self._on_nats_message)

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except Exception as e:
            logger.warning("NATS bridge failed to connect: %s (continuing without NATS)", e)
            self._nc = None

    async def stop(self) -> None:
        """Stop NATS bridge and unregister."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._nc and self._nc.is_connected:
            try:
                await self._publish_unregistration()
                await self._nc.drain()
            except Exception:
                pass

        self._nc = None
        logger.info("NATS bridge stopped: %s", self.agent_id)

    async def send_dm(self, to_agent: str, content: str) -> None:
        """Send a DM to another agent via NATS."""
        if not self._nc or not self._nc.is_connected:
            return
        msg = {
            "message_id": str(id(content)),
            "from_agent": self.agent_id,
            "to_agent": to_agent,
            "message_type": "agent_dm",
            "payload": {"content": content},
        }
        await self._nc.publish(
            f"agent.{to_agent}.inbox",
            json.dumps(msg).encode("utf-8"),
        )

    async def broadcast(self, content: str) -> None:
        """Broadcast a message to all agents."""
        if not self._nc or not self._nc.is_connected:
            return
        msg = {
            "message_id": str(id(content)),
            "from_agent": self.agent_id,
            "to_agent": "",
            "message_type": "agent_broadcast",
            "payload": {"content": content},
        }
        await self._nc.publish(
            "agent.broadcast",
            json.dumps(msg).encode("utf-8"),
        )

    # ---- Internal ----

    async def _inject_to_pty(self, content: str) -> bool:
        """Inject text into the PTY, adapting to the backend type."""
        if not self._pty:
            return False
        try:
            if self._pty_mode == "pty_chain":
                if hasattr(self._pty, "is_running") and self._pty.is_running:
                    await self._pty.inject_command(content)
                    return True
            elif self._pty_mode == "terminal_pty":
                if hasattr(self._pty, "is_monitoring") and self._pty.is_monitoring():
                    await self._pty.send_input((content + "\n").encode())
                    return True
        except Exception as e:
            logger.debug("PTY inject error: %s", e)
        return False

    async def _on_nats_message(self, msg) -> None:
        """Handle incoming NATS message — inject into PTY."""
        try:
            data = json.loads(msg.data.decode("utf-8"))
            mt = data.get("message_type", "")
            payload = data.get("payload", {})
            from_agent = data.get("from_agent", "")

            if mt in ("agent_dm", "task_create"):
                content = payload.get("content") or payload.get("description", "")
                if content:
                    ok = await self._inject_to_pty(content)
                    if ok:
                        logger.info(
                            "Injected %s from %s (%d chars)",
                            mt, from_agent, len(content),
                        )

            elif mt == "agent_broadcast":
                content = payload.get("content", "")
                if content == "__re_register__":
                    await self._publish_registration()

            elif mt == "shutdown_request":
                logger.info("Shutdown requested by %s", from_agent)
                self._running = False

        except Exception as e:
            logger.debug("NATS message handler error: %s", e)

    async def _on_terminal_event(self, event) -> None:
        """Callback for TerminalPTY events — track output."""
        try:
            if hasattr(event, "event_type") and str(event.event_type.value) == "output":
                self._on_shell_output(event.data)
        except Exception:
            pass

    def _on_shell_output(self, data: bytes) -> None:
        """Callback from PTYChain — track output for monitoring."""
        self._output_ring.extend(data)
        if len(self._output_ring) > _OUTPUT_RING_SIZE:
            self._output_ring = self._output_ring[-_OUTPUT_RING_SIZE:]

    async def _publish_registration(self) -> None:
        """Publish agent registration to NATS discovery."""
        if not self._nc or not self._nc.is_connected:
            return
        msg = {
            "from_agent": self.agent_id,
            "to_agent": "",
            "message_type": "agent_register",
            "payload": {"agent_id": self.agent_id, "role": self.role},
        }
        await self._nc.publish(
            "agent.discovery",
            json.dumps(msg).encode("utf-8"),
        )

    async def _publish_unregistration(self) -> None:
        """Publish agent unregistration."""
        if not self._nc or not self._nc.is_connected:
            return
        msg = {
            "from_agent": self.agent_id,
            "to_agent": "",
            "message_type": "agent_unregister",
            "payload": {"agent_id": self.agent_id},
        }
        await self._nc.publish(
            "agent.discovery",
            json.dumps(msg).encode("utf-8"),
        )

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat + status."""
        try:
            while self._running:
                await asyncio.sleep(10.0)
                if self._nc and self._nc.is_connected:
                    output_text = self._output_ring.decode("utf-8", errors="replace")
                    line_count = output_text.count("\n")
                    hb = {
                        "from_agent": self.agent_id,
                        "to_agent": "",
                        "message_type": "agent_heartbeat",
                        "payload": {
                            "agent_id": self.agent_id,
                            "line_count": line_count,
                        },
                    }
                    await self._nc.publish(
                        "agent.heartbeat",
                        json.dumps(hb).encode("utf-8"),
                    )
        except asyncio.CancelledError:
            pass
