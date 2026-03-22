"""Shared NATS transport utilities for AetherTerm components.

Provides common message helpers, subject constants, and connection factory
used by ControlServer (NATSController), AgentServer (NATSControlBridge),
and AgentShell (LogSender).

"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger("aetherterm.nats_transport")

# ---------------------------------------------------------------------------
# Lazy nats import
# ---------------------------------------------------------------------------
try:
    import nats as _nats_lib  # noqa: F401

    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Default connection
# ---------------------------------------------------------------------------
DEFAULT_NATS_URL = "nats://localhost:4222"


def get_nats_url() -> str:
    """Return NATS server URL from environment or default."""
    return os.environ.get("NATS_URL", DEFAULT_NATS_URL)


# ---------------------------------------------------------------------------
# Subject namespace
# ---------------------------------------------------------------------------
SUBJECT_PREFIX = "aether.terminal"


class Subjects:
    """NATS subject constants following {namespace}.{subject}.{verb} convention."""

    # AgentServer -> ControlServer
    @staticmethod
    def agentserver_register(agent_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentserver.{agent_id}.register"

    @staticmethod
    def agentserver_heartbeat(agent_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentserver.{agent_id}.heartbeat"

    @staticmethod
    def agentserver_report_session(agent_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentserver.{agent_id}.report.session"

    @staticmethod
    def agentserver_forward_log(agent_id: str, session_id: str, pane_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentserver.{agent_id}.forward.log.{session_id}.{pane_id}"

    # AgentShell -> ControlServer
    @staticmethod
    def agentshell_register(session_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentshell.{session_id}.register"

    @staticmethod
    def agentshell_heartbeat(session_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentshell.{session_id}.heartbeat"

    @staticmethod
    def agentshell_forward_log(session_id: str) -> str:
        return f"{SUBJECT_PREFIX}.agentshell.{session_id}.forward.log"

    # ControlServer -> AgentServer
    @staticmethod
    def controlserver_command(agent_id: str) -> str:
        return f"{SUBJECT_PREFIX}.controlserver.command.{agent_id}"

    @staticmethod
    def controlserver_broadcast() -> str:
        return f"{SUBJECT_PREFIX}.controlserver.broadcast"

    # Wildcard subscriptions (ControlServer side)
    @staticmethod
    def all_agentserver_register() -> str:
        return f"{SUBJECT_PREFIX}.agentserver.*.register"

    @staticmethod
    def all_agentserver_heartbeat() -> str:
        return f"{SUBJECT_PREFIX}.agentserver.*.heartbeat"

    @staticmethod
    def all_agentserver_report_session() -> str:
        return f"{SUBJECT_PREFIX}.agentserver.*.report.session"

    @staticmethod
    def all_agentserver_forward_log() -> str:
        """Subscribe to all log forwarding: aether.terminal.agentserver.*.forward.log.>"""
        return f"{SUBJECT_PREFIX}.agentserver.*.forward.log.>"

    @staticmethod
    def all_agentshell_register() -> str:
        return f"{SUBJECT_PREFIX}.agentshell.*.register"

    @staticmethod
    def all_agentshell_heartbeat() -> str:
        return f"{SUBJECT_PREFIX}.agentshell.*.heartbeat"

    @staticmethod
    def all_agentshell_forward_log() -> str:
        return f"{SUBJECT_PREFIX}.agentshell.*.forward.log"


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def pack_message(msg: Dict[str, Any]) -> bytes:
    """Serialize a message dict to JSON bytes."""
    return json.dumps(msg, default=_json_default).encode("utf-8")


def unpack_message(data: bytes) -> Dict[str, Any]:
    """Deserialize JSON bytes to a message dict."""
    return json.loads(data)


def make_envelope(
    msg_type: str,
    sender_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a standard message envelope with timestamp."""
    return {
        "type": msg_type,
        "sender_id": sender_id,
        "timestamp": time.time(),
        "payload": payload,
    }


def _json_default(obj: Any) -> Any:
    """JSON serializer fallback for bytes and other types."""
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

async def connect_nats(
    name: str = "aetherterm",
    nats_url: Optional[str] = None,
    max_reconnect_attempts: int = -1,
    reconnect_time_wait: float = 2.0,
) -> Any:
    """Create and return a connected NATS client.

    Args:
        name: Client name for NATS server identification.
        nats_url: NATS server URL. Falls back to NATS_URL env var.
        max_reconnect_attempts: -1 for infinite reconnect.
        reconnect_time_wait: Seconds between reconnect attempts.

    Returns:
        Connected nats.aio.client.Client instance.

    Raises:
        ImportError: If nats-py is not installed.
        Exception: If connection fails.
    """
    if not NATS_AVAILABLE:
        raise ImportError("nats-py is not installed. Install with: pip install nats-py")

    import nats as nats_lib

    url = nats_url or get_nats_url()

    async def _on_disconnect():
        log.warning("NATS disconnected: %s", name)

    async def _on_reconnect():
        log.info("NATS reconnected: %s", name)

    async def _on_error(e: Exception):
        log.error("NATS error (%s): %s", name, e)

    nc = await nats_lib.connect(
        servers=url,
        name=name,
        max_reconnect_attempts=max_reconnect_attempts,
        reconnect_time_wait=reconnect_time_wait,
        disconnected_cb=_on_disconnect,
        reconnected_cb=_on_reconnect,
        error_cb=_on_error,
    )
    log.info("NATS connected: %s -> %s", name, url)
    return nc
