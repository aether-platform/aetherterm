"""NATSControlBridge -- AgentServer NATS communication with ControlServer.

Provides:
- Heartbeat publishing
- Session report publishing
- Log forwarding (batched)
- Control command subscription

Publishes:
    aether.terminal.agentserver.{agent_id}.register
    aether.terminal.agentserver.{agent_id}.heartbeat
    aether.terminal.agentserver.{agent_id}.report.session
    aether.terminal.agentserver.{agent_id}.forward.log.{session_id}.{pane_id}

Subscribes:
    aether.terminal.controlserver.command.{agent_id}
    aether.terminal.controlserver.broadcast
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from typing import Any, Awaitable, Callable, Dict, List

from aetherterm.common.nats_transport import (
    NATS_AVAILABLE,
    Subjects,
    connect_nats,
    make_envelope,
    pack_message,
    unpack_message,
)

log = logging.getLogger("aetherterm.nats_bridge")

ControlCommandCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]


class NATSControlBridge:
    """NATS bridge between AgentServer and ControlServer.

    The bridge batches log forwarding (LOG_BATCH_INTERVAL seconds) and
    sends periodic heartbeats (HEARTBEAT_INTERVAL seconds).
    """

    LOG_BATCH_INTERVAL: float = 0.1
    HEARTBEAT_INTERVAL: float = 15.0

    def __init__(
        self,
        nats_url: str = "",
        agent_server_id: str = "",
    ) -> None:
        self._nats_url = nats_url
        self.agent_server_id = agent_server_id or self._default_agent_id()

        self._nc: Any = None
        self._subscriptions: list = []

        # State
        self._running = False
        self._connected = False
        self._tasks: List[asyncio.Task] = []
        self._callbacks: List[ControlCommandCallback] = []

        # Log batching buffer: {(session_id, pane_id): [data_chunks]}
        self._log_buffer: Dict[tuple[str, str], List[bytes]] = {}
        self._log_buffer_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Connect to NATS and start background loops.

        Returns True if connected, False if nats-py is unavailable.
        """
        if not NATS_AVAILABLE:
            log.warning("nats-py not available -- NATSControlBridge will not start")
            return False

        try:
            self._nc = await connect_nats(
                name=f"agentserver-{self.agent_server_id}",
                nats_url=self._nats_url or None,
            )

            self._running = True
            self._connected = True

            # Subscribe to commands targeted at this agent
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.controlserver_command(self.agent_server_id),
                    cb=self._on_command,
                )
            )
            # Subscribe to broadcast commands
            self._subscriptions.append(
                await self._nc.subscribe(
                    Subjects.controlserver_broadcast(),
                    cb=self._on_command,
                )
            )

            # Background loops
            self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
            self._tasks.append(asyncio.create_task(self._log_flush_loop()))

            # Send initial registration
            await self._publish(
                Subjects.agentserver_register(self.agent_server_id),
                make_envelope(
                    "agent_register",
                    self.agent_server_id,
                    {"hostname": platform.node()},
                ),
            )

            return True

        except Exception:
            log.exception("Failed to start NATSControlBridge")
            self._running = False
            self._connected = False
            return False

    async def stop(self) -> None:
        """Gracefully shut down."""
        self._running = False
        self._connected = False

        await self._flush_log_buffer()

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        self._subscriptions.clear()

        if self._nc and self._nc.is_connected:
            await self._nc.drain()
            self._nc = None

        log.info("NATSControlBridge stopped")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._running and self._nc is not None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_control_command(self, callback: ControlCommandCallback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_control_command(self, callback: ControlCommandCallback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # ------------------------------------------------------------------
    # Outbound: AgentServer -> ControlServer
    # ------------------------------------------------------------------

    async def forward_log(
        self, session_id: str, pane_id: str, data: bytes
    ) -> None:
        """Buffer terminal output for batched forwarding."""
        if not self._running:
            return
        key = (session_id, pane_id)
        async with self._log_buffer_lock:
            self._log_buffer.setdefault(key, []).append(data)

    async def send_session_report(self, sessions: List[Dict[str, Any]]) -> None:
        """Report current session state to ControlServer."""
        if not self._running:
            return
        await self._publish(
            Subjects.agentserver_report_session(self.agent_server_id),
            make_envelope(
                "session_report",
                self.agent_server_id,
                {"sessions": sessions},
            ),
        )

    async def publish_event(
        self, topic: str, event_type: str, payload: Dict[str, Any]
    ) -> None:
        """Publish an arbitrary event."""
        if not self._running:
            return
        # Map old topic-style to NATS subject
        subject = f"aether.terminal.agentserver.{self.agent_server_id}.event.{topic}"
        await self._publish(
            subject,
            make_envelope(event_type, self.agent_server_id, payload),
        )

    async def send_heartbeat(self) -> None:
        """Send a single heartbeat."""
        if not self._running:
            return
        await self._publish(
            Subjects.agentserver_heartbeat(self.agent_server_id),
            make_envelope(
                "heartbeat",
                self.agent_server_id,
                {"uptime": time.monotonic()},
            ),
        )

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def _on_command(self, msg) -> None:
        """Handle inbound control commands from ControlServer."""
        try:
            data = unpack_message(msg.data)
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            log.debug("Received control command: %s", msg_type)

            if msg_type in ("kill_session", "block_input", "unblock_input", "emergency_stop"):
                log.info("Control command: %s (from=%s)", msg_type, data.get("sender_id", "?"))

            for cb in self._callbacks:
                try:
                    await cb(msg_type, payload)
                except Exception:
                    log.exception("Callback error handling '%s'", msg_type)

        except Exception:
            log.exception("Error handling NATS command")

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                await self.send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Heartbeat loop error")
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    async def _log_flush_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.LOG_BATCH_INTERVAL)
                await self._flush_log_buffer()
            except asyncio.CancelledError:
                await self._flush_log_buffer()
                break
            except Exception:
                log.exception("Log flush loop error")
                await asyncio.sleep(self.LOG_BATCH_INTERVAL)

    async def _flush_log_buffer(self) -> None:
        async with self._log_buffer_lock:
            if not self._log_buffer:
                return
            snapshot = dict(self._log_buffer)
            self._log_buffer.clear()

        for (session_id, pane_id), chunks in snapshot.items():
            merged = b"".join(chunks)
            if not merged:
                continue
            subject = Subjects.agentserver_forward_log(
                self.agent_server_id, session_id, pane_id
            )
            await self._publish(
                subject,
                make_envelope(
                    "log_forward",
                    self.agent_server_id,
                    {
                        "session_id": session_id,
                        "pane_id": pane_id,
                        "data": merged,
                    },
                ),
            )

    # ------------------------------------------------------------------
    # Low-level publish
    # ------------------------------------------------------------------

    async def _publish(self, subject: str, msg: Dict[str, Any]) -> bool:
        if self._nc is None or not self._running:
            return False
        try:
            await self._nc.publish(subject, pack_message(msg))
            return True
        except Exception as exc:
            log.warning("NATS publish error on %s: %s", subject, exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_agent_id() -> str:
        hostname = platform.node() or "unknown"
        pid = os.getpid()
        return f"agentserver-{hostname}-{pid}"
