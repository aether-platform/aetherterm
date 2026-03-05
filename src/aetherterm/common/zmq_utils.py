"""Shared ZMQ message utilities for AetherTerm components.

Provides common pack/unpack/envelope helpers and constants used by
ControlServer, AgentServer (ControlBridge), and AgentShell (LogSender).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Coroutine, Dict, Optional

log = logging.getLogger("aetherterm.zmq_utils")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SOCKET_LINGER_MS: int = 500
HEARTBEAT_INTERVAL_SEC: float = 15.0

# ---------------------------------------------------------------------------
# Lazy ZMQ / msgpack import
# ---------------------------------------------------------------------------
try:
    import msgpack

    _MSGPACK_AVAILABLE = True
except ImportError:
    _MSGPACK_AVAILABLE = False

try:
    import zmq  # noqa: F401
    import zmq.asyncio  # noqa: F401

    _ZMQ_AVAILABLE = True
except ImportError:
    _ZMQ_AVAILABLE = False

ZMQ_AVAILABLE: bool = _ZMQ_AVAILABLE and _MSGPACK_AVAILABLE


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def pack_message(msg: Dict[str, Any]) -> bytes:
    """Serialize a message dict to msgpack bytes."""
    return msgpack.packb(msg, use_bin_type=True)


def unpack_message(data: bytes) -> Dict[str, Any]:
    """Deserialize msgpack bytes to a message dict."""
    return msgpack.unpackb(data, raw=False)


def make_envelope(
    msg_type: str,
    agent_server_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a standard message envelope with timestamp."""
    return {
        "type": msg_type,
        "agent_server_id": agent_server_id,
        "timestamp": time.time(),
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Asyncio task safety wrapper
# ---------------------------------------------------------------------------

def safe_create_task(
    coro: Coroutine,
    *,
    name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> asyncio.Task:
    """Create an asyncio task that logs exceptions instead of silently dropping them.

    Use this instead of bare ``asyncio.create_task()`` for fire-and-forget coroutines.
    """
    task = asyncio.create_task(coro, name=name)
    _logger = logger or log

    def _done_callback(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            _logger.error(
                "Background task %s failed: %s",
                name or t.get_name(),
                exc,
                exc_info=exc,
            )

    task.add_done_callback(_done_callback)
    return task
