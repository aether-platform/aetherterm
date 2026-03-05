"""MessageRouter — per-agent inbox with idle-triggered delivery.

Fire-and-forget messaging with queue-based delivery:
- Messages to busy agents are queued in their inbox
- When an agent transitions to idle, queued messages are delivered
- Supports DM (direct) and broadcast (all agents except sender)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ....common.agent_protocol import AgentMessage, MessageType

log = logging.getLogger("aetherterm.messaging.router")

MAX_INBOX_SIZE = 1000


@dataclass
class AgentInbox:
    """Per-agent message inbox with delivery state."""

    agent_id: str
    queue: deque = field(default_factory=lambda: deque(maxlen=MAX_INBOX_SIZE))
    is_idle: bool = True
    last_activity: float = field(default_factory=time.time)
    ws_send_callback: Optional[Callable] = None


class MessageRouter:
    """Central message router with per-agent inbox and idle-triggered delivery.

    Routing logic:
    1. to_agent == "" or message_type == AGENT_BROADCAST → all agents (except sender)
    2. Recipient is idle → immediate delivery
    3. Recipient is busy → enqueue in inbox
    4. set_agent_idle() → flush queued messages
    """

    def __init__(self):
        self._inboxes: Dict[str, AgentInbox] = {}
        self._lock = asyncio.Lock()

    async def register_agent(
        self,
        agent_id: str,
        ws_send_callback: Optional[Callable] = None,
    ) -> None:
        """Register an agent with a WebSocket delivery callback."""
        async with self._lock:
            self._inboxes[agent_id] = AgentInbox(
                agent_id=agent_id,
                ws_send_callback=ws_send_callback,
            )
        log.info(f"Agent registered: {agent_id}")

    async def unregister_agent(self, agent_id: str) -> None:
        """Remove agent and discard its inbox."""
        async with self._lock:
            self._inboxes.pop(agent_id, None)
        log.info(f"Agent unregistered: {agent_id}")

    async def set_agent_idle(self, agent_id: str) -> None:
        """Mark agent as idle and deliver all queued messages."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return
        inbox.is_idle = True
        inbox.last_activity = time.time()
        log.debug(f"Agent {agent_id} → idle (queue={len(inbox.queue)})")
        await self._deliver_queued(agent_id)

    async def set_agent_busy(self, agent_id: str) -> None:
        """Mark agent as busy. Messages will be queued."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return
        inbox.is_idle = False
        inbox.last_activity = time.time()
        log.debug(f"Agent {agent_id} → busy")

    async def route_message(self, msg: AgentMessage) -> None:
        """Route a message: DM to specific agent or broadcast to all (except sender)."""
        is_broadcast = (
            not msg.to_agent or msg.message_type == MessageType.AGENT_BROADCAST
        )

        if is_broadcast:
            for agent_id in list(self._inboxes.keys()):
                if agent_id != msg.from_agent:
                    await self._enqueue_or_deliver(agent_id, msg)
            log.debug(
                f"Broadcast from {msg.from_agent} to {len(self._inboxes) - 1} agents"
            )
        else:
            await self._enqueue_or_deliver(msg.to_agent, msg)
            log.debug(f"DM from {msg.from_agent} → {msg.to_agent}")

    async def _enqueue_or_deliver(self, agent_id: str, msg: AgentMessage) -> None:
        """Deliver immediately if agent is idle, otherwise queue."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            log.warning(f"Message to unknown agent {agent_id}, dropped")
            return

        if inbox.is_idle:
            await self._deliver_message(inbox, msg)
        else:
            inbox.queue.append(msg)
            log.debug(
                f"Queued message for busy agent {agent_id} "
                f"(queue={len(inbox.queue)})"
            )

    async def _deliver_queued(self, agent_id: str) -> None:
        """Deliver all queued messages to an agent."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return

        while inbox.queue and inbox.is_idle:
            msg = inbox.queue.popleft()
            await self._deliver_message(inbox, msg)

    async def _deliver_message(self, inbox: AgentInbox, msg: AgentMessage) -> None:
        """Deliver a single message via WebSocket callback."""
        try:
            if inbox.ws_send_callback is not None:
                await inbox.ws_send_callback(msg)
            else:
                log.warning(
                    f"No delivery channel for agent {inbox.agent_id}, "
                    f"message dropped"
                )
        except Exception:
            log.exception(f"Delivery error for agent {inbox.agent_id}")

    def list_agents(self) -> List[dict]:
        """Return list of registered agents with their state."""
        return [
            {
                "agent_id": inbox.agent_id,
                "is_idle": inbox.is_idle,
                "queue_size": len(inbox.queue),
                "last_activity": inbox.last_activity,
            }
            for inbox in self._inboxes.values()
        ]

    def get_inbox(self, agent_id: str) -> Optional[AgentInbox]:
        """Get inbox for a specific agent."""
        return self._inboxes.get(agent_id)
