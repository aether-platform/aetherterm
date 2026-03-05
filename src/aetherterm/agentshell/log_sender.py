"""Lightweight ZMQ PUSH log sender for AgentShell.

Sends terminal output directly to ControlServer for cross-cutting AI analysis.
Fire-and-forget: no responses expected, graceful fallback if ControlServer unavailable.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_zmq: Optional[object] = None
_msgpack: Optional[object] = None

DEFAULT_PULL_URL = "tcp://localhost:8768"
BATCH_INTERVAL_SEC = 0.1  # 100 ms


def _ensure_deps() -> bool:
    """Try to import pyzmq and msgpack. Return True if both available."""
    global _zmq, _msgpack  # noqa: PLW0603
    if _zmq is not None and _msgpack is not None:
        return True
    try:
        import msgpack as _mp
        import zmq as _z
        _zmq = _z
        _msgpack = _mp
        return True
    except ImportError:
        return False


class LogSender:
    """Fire-and-forget ZMQ PUSH sender for terminal output.

    Usage::
        sender = LogSender(session_id="abc-123")
        await sender.start()
        await sender.send_output(data)
        await sender.stop()
    """

    def __init__(
        self,
        pull_url: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._pull_url = pull_url or os.environ.get(
            "CONTROL_SERVER_PULL", DEFAULT_PULL_URL
        )
        self._session_id = session_id or "unknown"
        self._ctx: object | None = None
        self._socket: object | None = None
        self._running = False
        self._buffer = bytearray()
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Connect the PUSH socket to the ControlServer PULL endpoint."""
        if self._running:
            return
        if not _ensure_deps():
            logger.warning("pyzmq or msgpack not installed -- LogSender disabled")
            return
        import zmq
        import zmq.asyncio
        try:
            self._ctx = zmq.asyncio.Context()
            self._socket = self._ctx.socket(zmq.PUSH)
            self._socket.setsockopt(zmq.SNDHWM, 1000)
            self._socket.setsockopt(zmq.LINGER, 0)
            self._socket.connect(self._pull_url)
            self._running = True
            self._flush_task = asyncio.create_task(self._batch_loop())
            logger.info(f"LogSender connected to {self._pull_url}")
        except Exception:
            logger.exception("LogSender failed to start -- disabled")
            self._running = False

    async def stop(self) -> None:
        """Flush remaining buffer and close the socket."""
        if not self._running:
            return
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        if self._socket:
            self._socket.close(linger=0)
            self._socket = None
        if self._ctx:
            self._ctx.term()
            self._ctx = None
        logger.info("LogSender stopped")

    async def send_output(self, data: bytes) -> None:
        """Buffer terminal output for batched sending."""
        if not self._running:
            return
        async with self._lock:
            self._buffer.extend(data)

    async def flush(self) -> None:
        """Force-flush buffered data to the PUSH socket."""
        async with self._lock:
            if not self._buffer:
                return
            payload = bytes(self._buffer)
            self._buffer.clear()
        await self._send_message(payload)

    async def _batch_loop(self) -> None:
        """Periodically flush buffered output every BATCH_INTERVAL_SEC."""
        try:
            while self._running:
                await asyncio.sleep(BATCH_INTERVAL_SEC)
                if self._running:
                    await self.flush()
        except asyncio.CancelledError:
            pass

    async def _send_message(self, data: bytes) -> None:
        """Serialize and send a single shell_output message via msgpack."""
        if not self._socket or not data:
            return
        from aetherterm.common.zmq_utils import pack_message

        msg = {
            "type": "shell_output",
            "session_id": self._session_id,
            "timestamp": time.time(),
            "data": data,
        }
        try:
            packed = pack_message(msg)
            await self._socket.send(packed, flags=1)  # zmq.NOBLOCK
        except Exception:
            logger.debug("LogSender: send failed (ControlServer may be down)")

    @property
    def is_running(self) -> bool:
        return self._running
