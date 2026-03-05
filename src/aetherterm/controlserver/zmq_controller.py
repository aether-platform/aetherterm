"""ZMQController -- ControlServer ZMQ transport layer.

Sockets (all bind on ControlServer side):
    ROUTER  (bind :8766) <-> AgentServer DEALER:  bidirectional control/RPC
    PUB     (bind :8767)  -> AgentServer SUB:     broadcast (emergency stop etc.)
    SUB     (bind :8769) <-  AgentServer PUB:     log/event streaming (one-way)

Session mapping:
    Tracks PTY sessions reported by AgentServers and AgentShell instances
    attached to those sessions.  Enables ControlServer to send commands to
    either AgentServer or AgentShell by session_id or shell_id.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aetherterm.common.models import PtySessionInfo, ShellInfo
from aetherterm.common.zmq_utils import pack_message, unpack_message

log = logging.getLogger("aetherterm.zmq_controller")

# Lazy ZMQ import -- ControlServer can start without pyzmq installed.
try:
    import zmq
    import zmq.asyncio

    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    log.info("pyzmq not available -- ZMQController disabled")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
LogCallback = Callable[[str, list], Awaitable[None]]
"""async (agent_server_id, log_entries) -> None"""

SessionReportCallback = Callable[[str, dict], Awaitable[None]]
"""async (agent_server_id, report) -> None"""

EventCallback = Callable[[str, str, dict], Awaitable[None]]
"""async (agent_server_id, event_type, payload) -> None"""


# ---------------------------------------------------------------------------
# ZMQController
# ---------------------------------------------------------------------------

class ZMQController:
    """ControlServer ZMQ transport with session mapping.

    Binds three sockets so AgentServers connect to them:
        ROUTER (:8766) -- bidirectional command/response
        PUB    (:8767) -- broadcast to all AgentServers
        SUB    (:8769) -- receive log/event stream from AgentServers
    """

    SOCKET_LINGER: int = 500
    HEARTBEAT_INTERVAL: float = 15.0

    def __init__(
        self,
        router_bind: str = "",
        pub_bind: str = "",
        sub_bind: str = "",
        pull_bind: str = "",
    ) -> None:
        self.router_bind = router_bind or os.environ.get(
            "ZMQ_ROUTER_BIND", "tcp://*:8766"
        )
        self.pub_bind = pub_bind or os.environ.get(
            "ZMQ_PUB_BIND", "tcp://*:8767"
        )
        self.sub_bind = sub_bind or os.environ.get(
            "ZMQ_SUB_BIND", "tcp://*:8769"
        )
        self.pull_bind = pull_bind or os.environ.get(
            "ZMQ_PULL_BIND", "tcp://*:8768"
        )

        # ZMQ internals
        self._ctx: Any = None
        self._router: Any = None
        self._pub: Any = None
        self._sub: Any = None
        self._pull: Any = None

        # State
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # Registered AgentServers: agent_server_id -> last_heartbeat timestamp
        self._agents: Dict[str, float] = {}

        # Session mapping
        self._sessions: Dict[str, PtySessionInfo] = {}   # session_id -> info
        self._shells: Dict[str, ShellInfo] = {}           # shell_id -> info
        # Reverse index: agent_server_id -> set of session_ids
        self._agent_sessions: Dict[str, set[str]] = {}

        # Callbacks
        self._log_cb: Optional[LogCallback] = None
        self._session_report_cb: Optional[SessionReportCallback] = None
        self._event_cb: Optional[EventCallback] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_log_received(self, cb: LogCallback) -> None:
        self._log_cb = cb

    def on_session_report(self, cb: SessionReportCallback) -> None:
        self._session_report_cb = cb

    def on_event(self, cb: EventCallback) -> None:
        self._event_cb = cb

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        if not ZMQ_AVAILABLE:
            log.warning("ZMQ not available -- ZMQController will not start")
            return False

        try:
            self._ctx = zmq.asyncio.Context()

            # ROUTER -- bidirectional control
            self._router = self._ctx.socket(zmq.ROUTER)
            self._router.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._router.setsockopt(zmq.ROUTER_MANDATORY, 1)
            self._router.bind(self.router_bind)
            log.info(f"ROUTER bound to {self.router_bind}")

            # PUB -- broadcast to AgentServers
            self._pub = self._ctx.socket(zmq.PUB)
            self._pub.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._pub.setsockopt(zmq.SNDHWM, 5000)
            self._pub.bind(self.pub_bind)
            log.info(f"PUB bound to {self.pub_bind}")

            # SUB -- receive log/event stream from AgentServer PUB sockets
            self._sub = self._ctx.socket(zmq.SUB)
            self._sub.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            # Subscribe to all topics from AgentServers
            self._sub.subscribe(b"log:")
            self._sub.subscribe(b"session:")
            self._sub.subscribe(b"event:")
            self._sub.bind(self.sub_bind)
            log.info(f"SUB bound to {self.sub_bind}")

            # PULL -- receive direct log from AgentShell PUSH sockets
            self._pull = self._ctx.socket(zmq.PULL)
            self._pull.setsockopt(zmq.LINGER, self.SOCKET_LINGER)
            self._pull.setsockopt(zmq.RCVHWM, 5000)
            self._pull.bind(self.pull_bind)
            log.info(f"PULL bound to {self.pull_bind}")

            self._running = True

            # Background tasks
            self._tasks.append(asyncio.create_task(self._router_recv_loop()))
            self._tasks.append(asyncio.create_task(self._sub_recv_loop()))
            self._tasks.append(asyncio.create_task(self._pull_recv_loop()))

            return True

        except Exception:
            log.exception("Failed to start ZMQController")
            self._running = False
            return False

    async def stop(self) -> None:
        self._running = False

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        for sock in (self._pull, self._sub, self._pub, self._router):
            if sock is not None:
                sock.close(linger=0)
        self._pull = self._sub = self._pub = self._router = None

        if self._ctx is not None:
            self._ctx.term()
            self._ctx = None

        log.info("ZMQController stopped")

    @property
    def is_connected(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Outbound: ControlServer -> AgentServers
    # ------------------------------------------------------------------

    async def send_to_agent(
        self, agent_server_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a targeted command to a specific AgentServer via ROUTER."""
        if self._router is None or not self._running:
            return False

        envelope = {
            "type": msg_type,
            "agent_server_id": "controlserver",
            "timestamp": time.time(),
            "payload": payload,
        }
        try:
            await self._router.send_multipart(
                [agent_server_id.encode(), pack_message(envelope)],
                zmq.NOBLOCK,
            )
            return True
        except zmq.ZMQError as exc:
            log.warning(f"ROUTER send to {agent_server_id} failed: {exc}")
            return False

    async def broadcast(self, topic: str, msg_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all AgentServers via PUB socket."""
        if self._pub is None or not self._running:
            return

        envelope = {
            "type": msg_type,
            "agent_server_id": "controlserver",
            "timestamp": time.time(),
            "payload": payload,
        }
        try:
            await self._pub.send_multipart(
                [topic.encode(), pack_message(envelope)],
                zmq.NOBLOCK,
            )
        except zmq.ZMQError as exc:
            log.warning(f"PUB broadcast error: {exc}")

    # Convenience methods used by CentralController
    async def send_emergency_stop(self, reason: str = "") -> None:
        await self.broadcast(
            "broadcast:emergency",
            "emergency_stop",
            {"reason": reason},
        )

    async def send_block_input(
        self, session_id: str = "", pane_id: str = "", reason: str = ""
    ) -> None:
        await self.broadcast(
            "broadcast:block",
            "block_input",
            {"session_id": session_id, "pane_id": pane_id, "reason": reason},
        )

    async def send_unblock_input(
        self, session_id: str = "", pane_id: str = "", admin_user: str = ""
    ) -> None:
        await self.broadcast(
            "broadcast:unblock",
            "unblock_input",
            {"session_id": session_id, "pane_id": pane_id, "admin_user": admin_user},
        )

    async def send_to_session(
        self, session_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a command to the AgentServer that owns a specific PTY session."""
        info = self._sessions.get(session_id)
        if not info:
            log.warning(f"Session {session_id} not found in mapping")
            return False
        return await self.send_to_agent(info.agent_server_id, msg_type, payload)

    async def send_to_shell(
        self, shell_id: str, msg_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a command targeting a specific AgentShell (routed via its AgentServer)."""
        shell = self._shells.get(shell_id)
        if not shell:
            log.warning(f"Shell {shell_id} not found in mapping")
            return False
        payload["target_shell_id"] = shell_id
        return await self.send_to_agent(shell.agent_server_id, msg_type, payload)

    # ------------------------------------------------------------------
    # Session mapping queries
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> Optional[PtySessionInfo]:
        return self._sessions.get(session_id)

    def get_shell(self, shell_id: str) -> Optional[ShellInfo]:
        return self._shells.get(shell_id)

    def list_sessions(self) -> List[PtySessionInfo]:
        return list(self._sessions.values())

    def list_shells(self) -> List[ShellInfo]:
        return list(self._shells.values())

    def get_sessions_for_agent(self, agent_server_id: str) -> List[PtySessionInfo]:
        session_ids = self._agent_sessions.get(agent_server_id, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_shells_for_session(self, session_id: str) -> List[ShellInfo]:
        info = self._sessions.get(session_id)
        if not info:
            return []
        return [self._shells[sid] for sid in info.shell_ids if sid in self._shells]

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "transport": "zmq-direct",
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "shells": len(self._shells),
            "sockets": {
                "router": self.router_bind,
                "pub": self.pub_bind,
                "sub": self.sub_bind,
                "pull": self.pull_bind,
            },
        }

    # ------------------------------------------------------------------
    # Inbound: ROUTER receive loop
    # ------------------------------------------------------------------

    async def _router_recv_loop(self) -> None:
        """Receive messages from AgentServer DEALER sockets."""
        while self._running:
            try:
                frames = await self._router.recv_multipart()
                if len(frames) < 2:
                    continue

                identity = frames[0].decode()
                raw = frames[-1]
                msg = unpack_message(raw)
                await self._handle_router_msg(identity, msg)

            except asyncio.CancelledError:
                break
            except zmq.ZMQError as exc:
                if exc.errno == zmq.ETERM:
                    break
                log.warning(f"ROUTER recv error: {exc}")
                await asyncio.sleep(0.5)
            except Exception:
                log.exception("ROUTER recv loop error")
                await asyncio.sleep(0.5)

    async def _handle_router_msg(self, identity: str, msg: Dict[str, Any]) -> None:
        """Dispatch a message received on the ROUTER socket."""
        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})
        agent_id = msg.get("agent_server_id", identity)

        if msg_type == "agent_register":
            self._agents[agent_id] = time.time()
            log.info(f"Agent registered via ROUTER: {agent_id}")
            # Send registration ACK
            await self.send_to_agent(agent_id, "registration_confirmed", {
                "agent_server_id": agent_id,
            })

        elif msg_type == "heartbeat":
            self._agents[agent_id] = time.time()

        elif msg_type == "session_report":
            self._update_session_mapping(agent_id, payload)
            if self._session_report_cb:
                try:
                    await self._session_report_cb(agent_id, payload)
                except Exception:
                    log.exception("session_report callback error")

        elif msg_type == "log_forward":
            # Log forwarding via DEALER (fallback when PUB unavailable)
            entries = payload.get("data", b"")
            if self._log_cb:
                try:
                    await self._log_cb(agent_id, [entries] if entries else [])
                except Exception:
                    log.exception("log_received callback error")

        elif msg_type == "shell_register":
            self._register_shell(agent_id, payload)

        elif msg_type == "shell_detach":
            shell_id = payload.get("shell_id", "")
            self._unregister_shell(shell_id)

        else:
            log.debug(f"ROUTER msg from {agent_id}: {msg_type}")
            if self._event_cb:
                try:
                    await self._event_cb(agent_id, msg_type, payload)
                except Exception:
                    log.exception(f"event callback error for {msg_type}")

    # ------------------------------------------------------------------
    # Inbound: SUB receive loop (AgentServer PUB stream)
    # ------------------------------------------------------------------

    async def _sub_recv_loop(self) -> None:
        """Receive log/event stream from AgentServer PUB sockets."""
        while self._running:
            try:
                frames = await self._sub.recv_multipart()
                if len(frames) < 2:
                    continue

                topic = frames[0].decode()
                raw = frames[1]
                msg = unpack_message(raw)
                await self._handle_sub_msg(topic, msg)

            except asyncio.CancelledError:
                break
            except zmq.ZMQError as exc:
                if exc.errno == zmq.ETERM:
                    break
                log.warning(f"SUB recv error: {exc}")
                await asyncio.sleep(0.5)
            except Exception:
                log.exception("SUB recv loop error")
                await asyncio.sleep(0.5)

    async def _handle_sub_msg(self, topic: str, msg: Dict[str, Any]) -> None:
        """Dispatch a message received on the SUB socket."""
        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})
        agent_id = msg.get("agent_server_id", "")

        if topic.startswith("log:"):
            # Log stream: topic = "log:{session_id}:{pane_id}"
            data = payload.get("data", b"")
            session_id = payload.get("session_id", "")
            if self._log_cb and data:
                try:
                    await self._log_cb(agent_id, [data])
                except Exception:
                    log.exception("log_received callback error (SUB)")
            # Update session last_activity
            if session_id in self._sessions:
                self._sessions[session_id].last_activity = time.time()

        elif topic.startswith("session:"):
            # Session report via PUB
            self._update_session_mapping(agent_id, payload)
            if self._session_report_cb:
                try:
                    await self._session_report_cb(agent_id, payload)
                except Exception:
                    log.exception("session_report callback error (SUB)")

        elif topic.startswith("event:"):
            if self._event_cb:
                try:
                    await self._event_cb(agent_id, msg_type, payload)
                except Exception:
                    log.exception(f"event callback error (SUB) for {msg_type}")

    # ------------------------------------------------------------------
    # Inbound: PULL receive loop (AgentShell direct log)
    # ------------------------------------------------------------------

    async def _pull_recv_loop(self) -> None:
        """Receive shell_output messages from AgentShell PUSH sockets."""
        while self._running:
            try:
                raw = await self._pull.recv()
                if not raw:
                    continue

                msg = unpack_message(raw)
                await self._handle_pull_msg(msg)

            except asyncio.CancelledError:
                break
            except zmq.ZMQError as exc:
                if exc.errno == zmq.ETERM:
                    break
                log.warning(f"PULL recv error: {exc}")
                await asyncio.sleep(0.5)
            except Exception:
                log.exception("PULL recv loop error")
                await asyncio.sleep(0.5)

    async def _handle_pull_msg(self, msg: Dict[str, Any]) -> None:
        """Handle a shell_output message from AgentShell."""
        msg_type = msg.get("type", "")
        if msg_type != "shell_output":
            log.debug(f"PULL unexpected msg type: {msg_type}")
            return

        session_id = msg.get("session_id", "")
        data = msg.get("data", b"")
        if not data:
            return

        # Update session last_activity if mapped
        if session_id in self._sessions:
            self._sessions[session_id].last_activity = time.time()

        # Forward to log callback (same pipeline as PUB/SUB path)
        if self._log_cb:
            try:
                await self._log_cb(f"shell:{session_id}", [data])
            except Exception:
                log.exception("log_received callback error (PULL)")

    # ------------------------------------------------------------------
    # Session mapping updates
    # ------------------------------------------------------------------

    def _update_session_mapping(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """Update internal session mapping from an AgentServer report."""
        sessions = payload.get("sessions", [])
        if not sessions and "session_id" in payload:
            # Single-session update format
            sessions = [payload]

        reported_ids: set[str] = set()
        for s in sessions:
            sid = s.get("session_id", "")
            if not sid:
                continue
            reported_ids.add(sid)

            if sid in self._sessions:
                info = self._sessions[sid]
                info.last_activity = time.time()
                info.pane_ids = s.get("pane_ids", info.pane_ids)
            else:
                info = PtySessionInfo(
                    session_id=sid,
                    agent_server_id=agent_id,
                    pane_ids=s.get("pane_ids", []),
                )
                self._sessions[sid] = info
                log.info(f"New session mapped: {sid} on {agent_id}")

            # Update reverse index
            self._agent_sessions.setdefault(agent_id, set()).add(sid)

            # Update shell attachments if reported
            for shell_id in s.get("shell_ids", []):
                if shell_id not in self._shells:
                    self._shells[shell_id] = ShellInfo(
                        shell_id=shell_id,
                        session_id=sid,
                        agent_server_id=agent_id,
                    )
                    if shell_id not in info.shell_ids:
                        info.shell_ids.append(shell_id)

        # Prune sessions no longer reported by this agent
        existing = self._agent_sessions.get(agent_id, set())
        stale = existing - reported_ids
        for sid in stale:
            if sid in self._sessions:
                # Remove associated shells
                for shell_id in self._sessions[sid].shell_ids:
                    self._shells.pop(shell_id, None)
                del self._sessions[sid]
                log.info(f"Session removed from mapping: {sid}")
        if stale:
            self._agent_sessions[agent_id] = existing - stale

    def _register_shell(self, agent_id: str, payload: Dict[str, Any]) -> None:
        """Register an AgentShell instance in the session mapping."""
        shell_id = payload.get("shell_id", "")
        session_id = payload.get("session_id", "")
        if not shell_id or not session_id:
            return

        self._shells[shell_id] = ShellInfo(
            shell_id=shell_id,
            session_id=session_id,
            agent_server_id=agent_id,
        )

        # Link to session
        if session_id in self._sessions:
            if shell_id not in self._sessions[session_id].shell_ids:
                self._sessions[session_id].shell_ids.append(shell_id)

        log.info(f"Shell registered: {shell_id} -> session {session_id}")

    def _unregister_shell(self, shell_id: str) -> None:
        """Remove an AgentShell from the session mapping."""
        shell = self._shells.pop(shell_id, None)
        if shell and shell.session_id in self._sessions:
            session = self._sessions[shell.session_id]
            if shell_id in session.shell_ids:
                session.shell_ids.remove(shell_id)
        if shell:
            log.info(f"Shell unregistered: {shell_id}")
