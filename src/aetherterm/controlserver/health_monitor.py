"""HealthMonitor -- Agent heartbeat tracking and stale agent detection.

Periodically checks registered agents' last heartbeat timestamps and
removes agents that have exceeded the timeout threshold.  Emits events
when agents go stale or recover.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from .central_controller import CentralController

logger = logging.getLogger(__name__)

# Defaults (can be overridden via constructor)
DEFAULT_HEARTBEAT_TIMEOUT_SEC = 45.0  # 3x heartbeat interval (15s)
DEFAULT_CHECK_INTERVAL_SEC = 10.0
DEFAULT_STALE_REMOVAL_SEC = 120.0  # Remove after 2 min of no heartbeat


class AgentHealth:
    """Tracks a single agent's health state."""

    __slots__ = (
        "agent_id",
        "is_healthy",
        "last_heartbeat",
        "missed_count",
        "registered_at",
        "transport",
    )

    def __init__(self, agent_id: str, transport: str = "nats") -> None:
        self.agent_id = agent_id
        self.last_heartbeat = time.time()
        self.registered_at = time.time()
        self.is_healthy = True
        self.missed_count = 0
        self.transport = transport

    def record_heartbeat(self) -> bool:
        """Record a heartbeat. Returns True if agent was previously unhealthy."""
        was_unhealthy = not self.is_healthy
        self.last_heartbeat = time.time()
        self.is_healthy = True
        self.missed_count = 0
        return was_unhealthy

    def check(self, timeout: float) -> bool:
        """Check health. Returns True if still healthy."""
        elapsed = time.time() - self.last_heartbeat
        if elapsed > timeout:
            self.is_healthy = False
            self.missed_count += 1
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "agent_id": self.agent_id,
            "transport": self.transport,
            "is_healthy": self.is_healthy,
            "last_heartbeat_ago_sec": round(now - self.last_heartbeat, 1),
            "uptime_sec": round(now - self.registered_at, 1),
            "missed_count": self.missed_count,
        }


class HealthMonitor:
    """Monitors agent health via heartbeat tracking."""

    def __init__(
        self,
        controller: CentralController,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
        check_interval: float = DEFAULT_CHECK_INTERVAL_SEC,
        stale_removal: float = DEFAULT_STALE_REMOVAL_SEC,
    ) -> None:
        self._ctrl = controller
        self._heartbeat_timeout = heartbeat_timeout
        self._check_interval = check_interval
        self._stale_removal = stale_removal

        self._agents: Dict[str, AgentHealth] = {}
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info(
                f"HealthMonitor started (timeout={self._heartbeat_timeout}s, "
                f"check_interval={self._check_interval}s)"
            )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HealthMonitor stopped")

    # ------------------------------------------------------------------
    # Agent registration / heartbeat
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, transport: str = "nats") -> None:
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentHealth(agent_id, transport)
            logger.info(f"Agent registered in HealthMonitor: {agent_id} ({transport})")
        else:
            self._agents[agent_id].record_heartbeat()

    def record_heartbeat(self, agent_id: str) -> None:
        health = self._agents.get(agent_id)
        if health is None:
            self.register_agent(agent_id)
            return

        recovered = health.record_heartbeat()
        if recovered:
            logger.info(f"Agent recovered: {agent_id}")

    def unregister_agent(self, agent_id: str) -> None:
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Agent unregistered from HealthMonitor: {agent_id}")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_health(self, agent_id: str) -> Dict[str, Any] | None:
        health = self._agents.get(agent_id)
        return health.to_dict() if health else None

    def get_all_health(self) -> List[Dict[str, Any]]:
        return [h.to_dict() for h in self._agents.values()]

    def get_healthy_count(self) -> int:
        return sum(1 for h in self._agents.values() if h.is_healthy)

    def get_unhealthy_agents(self) -> List[str]:
        return [h.agent_id for h in self._agents.values() if not h.is_healthy]

    @property
    def total_agents(self) -> int:
        return len(self._agents)

    # ------------------------------------------------------------------
    # Monitor loop
    # ------------------------------------------------------------------

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_agents()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("HealthMonitor check error")
                await asyncio.sleep(self._check_interval)

    async def _check_agents(self) -> None:
        now = time.time()
        newly_unhealthy: List[str] = []
        to_remove: List[str] = []

        for agent_id, health in list(self._agents.items()):
            was_healthy = health.is_healthy
            is_healthy = health.check(self._heartbeat_timeout)

            if was_healthy and not is_healthy:
                newly_unhealthy.append(agent_id)
                logger.warning(
                    f"Agent unhealthy: {agent_id} "
                    f"(no heartbeat for {now - health.last_heartbeat:.0f}s)"
                )

            # Remove agents that have been stale for too long
            if not is_healthy:
                elapsed = now - health.last_heartbeat
                if elapsed > self._stale_removal:
                    to_remove.append(agent_id)

        # Remove stale agents
        for agent_id in to_remove:
            del self._agents[agent_id]
            logger.warning(f"Stale agent removed: {agent_id}")

            # Clean up from NATS controller's agent list
            if self._ctrl._nats_controller:
                self._ctrl._nats_controller._agents.pop(agent_id, None)

            # Also remove from legacy WebSocket agents
            self._ctrl.agent_servers.pop(agent_id, None)
            self._ctrl.nats_agents.pop(agent_id, None)

        # Notify admins about unhealthy agents
        if newly_unhealthy:
            await self._ctrl.broadcast_to_admins({
                "type": "agents_unhealthy",
                "agent_ids": newly_unhealthy,
                "timestamp": _iso_now(),
            })

        # Notify admins about removed agents
        if to_remove:
            await self._ctrl.broadcast_to_admins({
                "type": "agents_removed",
                "agent_ids": to_remove,
                "reason": "heartbeat_timeout",
                "timestamp": _iso_now(),
            })


def _iso_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
