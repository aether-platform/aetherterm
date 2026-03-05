"""
NATS client wrapper for AetherTerm components.

Provides connection management with auto-reconnect, JSON message
serialization, and structured subscription handling.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

import nats
from nats.aio.client import Client as NatsConnection
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]


class NatsClient:
    """NATS client with auto-reconnect and JSON messaging."""

    def __init__(
        self,
        servers: str = "nats://localhost:4222",
        name: str = "aetherterm",
        reconnect_time_wait: float = 2.0,
        max_reconnect_attempts: int = -1,
    ):
        self.servers = servers
        self.name = name
        self.reconnect_time_wait = reconnect_time_wait
        self.max_reconnect_attempts = max_reconnect_attempts

        self._nc: Optional[NatsConnection] = None
        self._subscriptions: list = []

    @property
    def is_connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    async def connect(self) -> None:
        """Connect to NATS server."""
        if self.is_connected:
            return

        self._nc = await nats.connect(
            servers=self.servers,
            name=self.name,
            reconnect_time_wait=self.reconnect_time_wait,
            max_reconnect_attempts=self.max_reconnect_attempts,
            disconnected_cb=self._on_disconnected,
            reconnected_cb=self._on_reconnected,
            error_cb=self._on_error,
        )
        logger.info(f"Connected to NATS: {self.servers} as '{self.name}'")

    async def close(self) -> None:
        """Close NATS connection."""
        if self._nc:
            await self._nc.drain()
            logger.info("NATS connection closed")
            self._nc = None
            self._subscriptions.clear()

    async def publish(self, subject: str, data: Dict[str, Any]) -> None:
        """Publish a JSON message to a subject."""
        if not self.is_connected:
            logger.warning(f"Not connected, dropping message to {subject}")
            return

        payload = json.dumps(data).encode()
        await self._nc.publish(subject, payload)
        logger.debug(f"Published to {subject}: {len(payload)} bytes")

    async def subscribe(self, subject: str, handler: MessageHandler) -> None:
        """Subscribe to a subject with a message handler.

        The handler receives (subject: str, data: dict).
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to NATS")

        async def _wrapper(msg: Msg) -> None:
            try:
                data = json.loads(msg.data.decode())
                await handler(msg.subject, data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON on {msg.subject}: {msg.data[:200]}")
            except Exception:
                logger.exception(f"Error handling message on {msg.subject}")

        sub = await self._nc.subscribe(subject, cb=_wrapper)
        self._subscriptions.append(sub)
        logger.info(f"Subscribed to {subject}")

    async def request(
        self, subject: str, data: Dict[str, Any], timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Send a request and wait for a reply (request-reply pattern)."""
        if not self.is_connected:
            return None

        payload = json.dumps(data).encode()
        try:
            response = await self._nc.request(subject, payload, timeout=timeout)
            return json.loads(response.data.decode())
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout on {subject}")
            return None
        except Exception:
            logger.exception(f"Request error on {subject}")
            return None

    # --- Connection callbacks ---

    async def _on_disconnected(self) -> None:
        logger.warning("NATS disconnected")

    async def _on_reconnected(self) -> None:
        logger.info("NATS reconnected")

    async def _on_error(self, e: Exception) -> None:
        logger.error(f"NATS error: {e}")
