"""Lightweight NATS log sender for AgentShell.

Sends terminal output directly to ControlServer for cross-cutting AI analysis.
Fire-and-forget: no responses expected, graceful fallback if ControlServer unavailable.

"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from aetherterm.common.nats_transport import (
    NATS_AVAILABLE,
    Subjects,
    connect_nats,
    make_envelope,
    pack_message,
)

logger = logging.getLogger(__name__)

BATCH_INTERVAL_SEC = 0.1  # 100 ms


class LogSender:
    """Fire-and-forget NATS sender for terminal output.

    Usage::
        sender = LogSender(session_id="abc-123")
        await sender.start()
        await sender.send_output(data)
        await sender.stop()
    """

    def __init__(
        self,
        nats_url: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._nats_url = nats_url or os.environ.get("NATS_URL", "nats://localhost:4222")
        self._session_id = session_id or "unknown"
        self._nc = None
        self._running = False
        self._buffer = bytearray()
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Connect to NATS for log forwarding."""
        if self._running:
            return
        if not NATS_AVAILABLE:
            logger.warning("nats-py not installed -- LogSender disabled")
            return
        try:
            self._nc = await connect_nats(
                name=f"agentshell-log-{self._session_id}",
                nats_url=self._nats_url,
            )
            self._running = True
            self._flush_task = asyncio.create_task(self._batch_loop())
            logger.info("LogSender connected to %s", self._nats_url)
        except Exception:
            logger.exception("LogSender failed to start -- disabled")
            self._running = False

    async def stop(self) -> None:
        """Flush remaining buffer and disconnect."""
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
        if self._nc and self._nc.is_connected:
            await self._nc.drain()
            self._nc = None
        logger.info("LogSender stopped")

    async def send_output(self, data: bytes) -> None:
        """Buffer terminal output for batched sending."""
        if not self._running:
            return
        async with self._lock:
            self._buffer.extend(data)

    async def flush(self) -> None:
        """Force-flush buffered data to NATS."""
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
        """Publish a single shell_output message via NATS."""
        if not self._nc or not data:
            return

        subject = Subjects.agentshell_forward_log(self._session_id)
        msg = make_envelope(
            "shell_output",
            f"shell:{self._session_id}",
            {
                "session_id": self._session_id,
                "timestamp": time.time(),
                "data": data,
            },
        )
        try:
            await self._nc.publish(subject, pack_message(msg))
        except Exception:
            logger.debug("LogSender: send failed (ControlServer may be down)")

    @property
    def is_running(self) -> bool:
        return self._running
