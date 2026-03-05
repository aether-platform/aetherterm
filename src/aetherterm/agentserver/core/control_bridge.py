"""ControlBridge -- ZMQ communication with ControlServer.

AgentServer (DEALER) <-> ControlServer (ROUTER): bidirectional control
AgentServer (SUB)    <-  ControlServer (PUB):    broadcast (emergency stop etc.)
AgentServer (PUB)     -> ControlServer (SUB):    log/event streaming (one-way)

The bridge is designed to be resilient: if ControlServer is unreachable the
AgentServer continues operating normally and reconnects automatically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
from typing import Any, Awaitable, Callable, Dict, List

from aetherterm.common.zmq_utils import make_envelope, pack_message, unpack_message

log = logging.getLogger("aetherterm.control_bridge")

# Lazy ZMQ import so AgentServer can start even without pyzmq installed.
try:
    import zmq
    import zmq.asyncio

    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    log.info("pyzmq not available -- ControlBridge disabled")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
ControlCommandCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]
"""Callback signature: async (command_type, payload) -> None"""


# ---------------------------------------------------------------------------
# ControlBridge
# ---------------------------------------------------------------------------


class ControlBridge:
    """ZMQ bridge between AgentServer and ControlServer.

    Sockets:
        DEALER -> ControlServer ROUTER  (bidirectional, request/reply style)
        SUB    <- ControlServer PUB     (broadcast, one-way)
        PUB    -> ControlServer SUB     (log/event streaming, one-way)

    The bridge batches log forwarding to limit traffic (``LOG_BATCH_INTERVAL``
    seconds) and sends periodic heartbeats (``HEARTBEAT_INTERVAL`` seconds).
    Log data is streamed via PUB socket with topic prefixes for efficient
    filtering on the ControlServer side.
    """

    # Tuning knobs
    LOG_BATCH_INTERVAL: float = 0.1  # seconds between log flushes
    HEARTBEAT_INTERVAL: float = 15.0  # seconds between heartbeats
    RECONNECT_DELAY: float = 5.0  # seconds before reconnect attempt
    SOCKET_LINGER: int = 500  # ms linger on close

    # Minimum expected frames in a SUB multipart message (topic + payload)
    _MIN_SUB_FRAMES: int = 2

    def __init__(
        self,
        router_url: str = "",
        pub_url: str = "",
        sub_bind_url: str = "",
        agent_server_id: str = "",
    ) -> None:
        """Initialize the ControlBridge.

        Args:
            router_url: ZMQ endpoint for the ControlServer ROUTER socket.
                Falls back to ``CONTROL_SERVER_ROUTER`` env var, then
                ``tcp://localhost:8766``.
            pub_url: ZMQ endpoint for the ControlServer PUB socket.
                Falls back to ``CONTROL_SERVER_PUB`` env var, then
                ``tcp://localhost:8767``.
            sub_bind_url: ZMQ endpoint for the ControlServer SUB socket
                (AgentServer publishes logs/events here).
                Falls back to ``CONTROL_SERVER_SUB`` env var, then
                ``tcp://localhost:8769``.
            agent_server_id: Unique identifier for this AgentServer instance.
                Auto-generated from hostname + PID if not provided.
        """
        self.router_url = router_url or os.environ.get(
            "CONTROL_SERVER_ROUTER", "tcp://localhost:8766"
        )
        self.pub_url = pub_url or os.environ.get("CONTROL_SERVER_PUB", "tcp://localhost:8767")
        self.sub_bind_url = sub_bind_url or os.environ.get(
            "CONTROL_SERVER_SUB", "tcp://localhost:8769"
        )
        self.agent_server_id = agent_server_id or self._default_agent_id()

        # ZMQ internals
        self._ctx: zmq.asyncio.Context | None = None
        self._dealer: Any = None
        self._sub: Any = None
        self._pub: Any = None  # PUB socket for log/event streaming

        # State
        self._running = False
        self._connected = False
        self._tasks: List[asyncio.Task] = []
        self._callbacks: List[ControlCommandCallback] = []

        # Log batching buffer:  {(session_id, pane_id): [data_chunks]}
        self._log_buffer: Dict[tuple[str, str], List[bytes]] = {}
        self._log_buffer_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Connect to ControlServer and start receive loops.

        Returns True if sockets were opened (even if the remote is not yet
        reachable -- ZMQ will reconnect transparently).  Returns False if
        pyzmq is not installed.
        """
        if not ZMQ_AVAILABLE:
            log.warning("ZMQ not available -- ControlBridge will not start")
            return False

        try:
            self._ctx = zmq.asyncio.Context()

            # DEALER socket -- bidirectional control channel
            self._dealer = self._ctx.socket(zmq.DEALER)
            self._dealer.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._dealer.setsockopt_string(zmq.IDENTITY, self.agent_server_id)
            self._dealer.setsockopt(zmq.RECONNECT_IVL, int(self.RECONNECT_DELAY * 1000))
            self._dealer.setsockopt(zmq.RECONNECT_IVL_MAX, 30_000)
            self._dealer.connect(self.router_url)
            log.info(f"DEALER connected to {self.router_url} (identity={self.agent_server_id})")

            # SUB socket -- broadcast channel (receive from ControlServer)
            self._sub = self._ctx.socket(zmq.SUB)
            self._sub.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._sub.setsockopt(zmq.RECONNECT_IVL, int(self.RECONNECT_DELAY * 1000))
            self._sub.setsockopt(zmq.RECONNECT_IVL_MAX, 30_000)
            # Subscribe to broadcasts targeting everyone and this specific server
            self._sub.subscribe(b"broadcast:")
            self._sub.subscribe(f"agent:{self.agent_server_id}:".encode())
            self._sub.connect(self.pub_url)
            log.info(f"SUB connected to {self.pub_url}")

            # PUB socket -- log/event streaming to ControlServer SUB
            self._pub = self._ctx.socket(zmq.PUB)
            self._pub.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._pub.setsockopt(zmq.SNDHWM, 5000)
            self._pub.setsockopt(zmq.RECONNECT_IVL, int(self.RECONNECT_DELAY * 1000))
            self._pub.setsockopt(zmq.RECONNECT_IVL_MAX, 30_000)
            self._pub.connect(self.sub_bind_url)
            log.info(f"PUB connected to {self.sub_bind_url}")

            self._running = True
            self._connected = True

            # Background loops
            self._tasks.append(asyncio.create_task(self._dealer_recv_loop()))
            self._tasks.append(asyncio.create_task(self._sub_recv_loop()))
            self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
            self._tasks.append(asyncio.create_task(self._log_flush_loop()))

            # Send initial registration
            await self._send_dealer(
                make_envelope(
                    "agent_register",
                    self.agent_server_id,
                    {"hostname": platform.node()},
                )
            )

            return True

        except Exception:
            log.exception("Failed to start ControlBridge")
            self._running = False
            self._connected = False
            return False

    async def stop(self) -> None:
        """Gracefully shut down sockets and background tasks."""
        self._running = False
        self._connected = False

        # Flush remaining logs before shutdown
        await self._flush_log_buffer()

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Close sockets
        if self._pub is not None:
            self._pub.close(linger=0)
            self._pub = None
        if self._dealer is not None:
            self._dealer.close(linger=0)
            self._dealer = None
        if self._sub is not None:
            self._sub.close(linger=0)
            self._sub = None
        if self._ctx is not None:
            self._ctx.term()
            self._ctx = None

        log.info("ControlBridge stopped")

    @property
    def is_connected(self) -> bool:
        """Whether the bridge sockets are active."""
        return self._connected and self._running

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_control_command(self, callback: ControlCommandCallback) -> None:
        """Register a handler for inbound control commands.

        The callback receives ``(command_type: str, payload: dict)``.
        Multiple callbacks may be registered; all are invoked for every
        inbound command.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_control_command(self, callback: ControlCommandCallback) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # ------------------------------------------------------------------
    # Outbound: AgentServer -> ControlServer
    # ------------------------------------------------------------------

    async def forward_log(
        self,
        session_id: str,
        pane_id: str,
        data: bytes,
    ) -> None:
        """Buffer terminal output for batched forwarding to ControlServer.

        Data is accumulated per (session_id, pane_id) and flushed every
        ``LOG_BATCH_INTERVAL`` seconds by the background flush loop.
        """
        if not self._running:
            return

        key = (session_id, pane_id)
        async with self._log_buffer_lock:
            self._log_buffer.setdefault(key, []).append(data)

    async def send_session_report(self, sessions: List[Dict[str, Any]]) -> None:
        """Report current session state to ControlServer.

        Publishes via PUB (topic ``session:report``) with DEALER fallback.
        """
        if not self._running:
            return

        envelope = make_envelope(
            "session_report",
            self.agent_server_id,
            {"sessions": sessions},
        )
        if not await self._send_pub("session:report", envelope):
            await self._send_dealer(envelope)

    async def publish_event(
        self, topic: str, event_type: str, payload: Dict[str, Any]
    ) -> None:
        """Publish an arbitrary event via PUB socket.

        Args:
            topic: PUB topic prefix (e.g. ``event:shell_attached``).
            event_type: Message type string.
            payload: Event payload dict.
        """
        if not self._running:
            return

        envelope = make_envelope(event_type, self.agent_server_id, payload)
        if not await self._send_pub(topic, envelope):
            await self._send_dealer(envelope)

    async def send_heartbeat(self) -> None:
        """Send a single heartbeat to ControlServer."""
        if not self._running:
            return

        await self._send_dealer(
            make_envelope(
                "heartbeat",
                self.agent_server_id,
                {"uptime": time.monotonic()},
            )
        )

    # ------------------------------------------------------------------
    # Inbound receive loops
    # ------------------------------------------------------------------

    async def _dealer_recv_loop(self) -> None:
        """Receive targeted commands from ControlServer via DEALER socket."""
        while self._running:
            try:
                frames = await self._dealer.recv_multipart()
                if not frames:
                    continue

                # DEALER receives [payload] (no identity prefix on the recv side)
                raw = frames[-1]
                msg = unpack_message(raw)
                await self._dispatch(msg)

            except asyncio.CancelledError:
                break
            except zmq.ZMQError as exc:
                if exc.errno == zmq.ETERM:
                    break
                log.warning(f"DEALER recv ZMQ error: {exc}")
                await asyncio.sleep(0.5)
            except Exception:
                log.exception("DEALER recv loop error")
                await asyncio.sleep(0.5)

    async def _sub_recv_loop(self) -> None:
        """Receive broadcast messages from ControlServer via SUB socket."""
        while self._running:
            try:
                frames = await self._sub.recv_multipart()
                if len(frames) < self._MIN_SUB_FRAMES:
                    continue

                # frames[0] = topic, frames[1] = msgpack payload
                raw = frames[1]
                msg = unpack_message(raw)
                await self._dispatch(msg)

            except asyncio.CancelledError:
                break
            except zmq.ZMQError as exc:
                if exc.errno == zmq.ETERM:
                    break
                log.warning(f"SUB recv ZMQ error: {exc}")
                await asyncio.sleep(0.5)
            except Exception:
                log.exception("SUB recv loop error")
                await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Inbound dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, msg: Dict[str, Any]) -> None:
        """Route an inbound message to the appropriate handler and callbacks."""
        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})

        log.debug(f"Received control command: {msg_type}")

        # Well-known command types are logged at info level
        if msg_type in (
            "kill_session",
            "block_input",
            "unblock_input",
            "emergency_stop",
        ):
            log.info(f"Control command: {msg_type} (from={msg.get('agent_server_id', '?')})")

        # Invoke all registered callbacks
        for cb in self._callbacks:
            try:
                await cb(msg_type, payload)
            except Exception:
                log.exception(f"Callback error handling '{msg_type}'")

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to ControlServer."""
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
        """Periodically flush the log buffer to ControlServer."""
        while self._running:
            try:
                await asyncio.sleep(self.LOG_BATCH_INTERVAL)
                await self._flush_log_buffer()
            except asyncio.CancelledError:
                # Final flush on cancellation
                await self._flush_log_buffer()
                break
            except Exception:
                log.exception("Log flush loop error")
                await asyncio.sleep(self.LOG_BATCH_INTERVAL)

    async def _flush_log_buffer(self) -> None:
        """Publish all buffered log data via PUB socket and clear the buffer.

        Each message is published with topic ``log:{session_id}:{pane_id}``
        so that the ControlServer SUB socket can filter by session.
        Falls back to DEALER if PUB is unavailable.
        """
        async with self._log_buffer_lock:
            if not self._log_buffer:
                return
            snapshot = dict(self._log_buffer)
            self._log_buffer.clear()

        for (session_id, pane_id), chunks in snapshot.items():
            merged = b"".join(chunks)
            if not merged:
                continue
            envelope = make_envelope(
                "log_forward",
                self.agent_server_id,
                {
                    "session_id": session_id,
                    "pane_id": pane_id,
                    "data": merged,
                },
            )
            topic = f"log:{session_id}:{pane_id}"
            if not await self._send_pub(topic, envelope):
                # Fallback to DEALER if PUB fails
                await self._send_dealer(envelope)

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    async def _send_dealer(self, msg: Dict[str, Any]) -> bool:
        """Serialize and send a message via the DEALER socket.

        Returns True on success, False on failure (logged as warning).
        """
        if self._dealer is None or not self._running:
            return False

        try:
            await self._dealer.send(pack_message(msg), zmq.NOBLOCK)
            return True
        except zmq.Again:
            log.debug("DEALER send would block (HWM reached), dropping message")
            return False
        except zmq.ZMQError as exc:
            log.warning(f"DEALER send error: {exc}")
            return False
        except Exception:
            log.exception("Unexpected DEALER send error")
            return False

    async def _send_pub(self, topic: str, msg: Dict[str, Any]) -> bool:
        """Publish a message on the PUB socket with a topic prefix.

        The message is sent as a two-frame multipart: [topic, msgpack_payload].
        Returns True on success, False on failure.
        """
        if self._pub is None or not self._running:
            return False

        try:
            await self._pub.send_multipart(
                [topic.encode(), pack_message(msg)], zmq.NOBLOCK
            )
            return True
        except zmq.Again:
            log.debug("PUB send would block (HWM reached), dropping message")
            return False
        except zmq.ZMQError as exc:
            log.warning(f"PUB send error: {exc}")
            return False
        except Exception:
            log.exception("Unexpected PUB send error")
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_agent_id() -> str:
        """Generate a default agent_server_id from hostname and PID."""
        hostname = platform.node() or "unknown"
        pid = os.getpid()
        return f"agentserver-{hostname}-{pid}"
