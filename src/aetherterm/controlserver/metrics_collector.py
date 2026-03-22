"""MetricsCollector -- System metrics for ControlServer.

Collects and exposes CPU, memory, connection counts, and log pipeline
statistics.  Designed for consumption by REST API health/metrics endpoints
and admin WebSocket broadcasts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from .central_controller import CentralController

logger = logging.getLogger(__name__)

# Collection interval
DEFAULT_COLLECT_INTERVAL_SEC = 15.0
MAX_HISTORY_POINTS = 60  # Keep last ~15 min at 15s interval


@dataclass
class MetricsSnapshot:
    """A single point-in-time metrics snapshot."""

    timestamp: float = 0.0

    # Process metrics
    cpu_percent: float = 0.0
    memory_rss_mb: float = 0.0
    memory_vms_mb: float = 0.0
    open_fds: int = 0

    # Connection metrics
    ws_agent_count: int = 0
    nats_agent_count: int = 0
    admin_client_count: int = 0
    active_session_count: int = 0
    active_block_count: int = 0

    # Health metrics
    healthy_agent_count: int = 0
    unhealthy_agent_count: int = 0

    # Log pipeline metrics
    buffered_log_lines: int = 0
    total_analyses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "process": {
                "cpu_percent": self.cpu_percent,
                "memory_rss_mb": round(self.memory_rss_mb, 1),
                "memory_vms_mb": round(self.memory_vms_mb, 1),
                "open_fds": self.open_fds,
            },
            "connections": {
                "ws_agents": self.ws_agent_count,
                "nats_agents": self.nats_agent_count,
                "admin_clients": self.admin_client_count,
                "active_sessions": self.active_session_count,
                "active_blocks": self.active_block_count,
            },
            "health": {
                "healthy_agents": self.healthy_agent_count,
                "unhealthy_agents": self.unhealthy_agent_count,
            },
            "log_pipeline": {
                "buffered_lines": self.buffered_log_lines,
                "total_analyses": self.total_analyses,
            },
        }


class MetricsCollector:
    """Periodically collects system and application metrics."""

    def __init__(
        self,
        controller: CentralController,
        collect_interval: float = DEFAULT_COLLECT_INTERVAL_SEC,
    ) -> None:
        self._ctrl = controller
        self._collect_interval = collect_interval
        self._history: List[MetricsSnapshot] = []
        self._task: asyncio.Task | None = None
        self._process = None  # psutil.Process (lazy)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._collect_loop())
            logger.info(f"MetricsCollector started (interval={self._collect_interval}s)")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MetricsCollector stopped")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_latest(self) -> Dict[str, Any] | None:
        if not self._history:
            return None
        return self._history[-1].to_dict()

    def get_history(self, count: int = 20) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._history[-count:]]

    def collect_now(self) -> MetricsSnapshot:
        """Collect a snapshot synchronously (for on-demand use)."""
        return self._collect_snapshot()

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    async def _collect_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._collect_interval)
                snapshot = self._collect_snapshot()
                self._history.append(snapshot)
                if len(self._history) > MAX_HISTORY_POINTS:
                    self._history = self._history[-MAX_HISTORY_POINTS:]
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("MetricsCollector error")
                await asyncio.sleep(self._collect_interval)

    def _collect_snapshot(self) -> MetricsSnapshot:
        snap = MetricsSnapshot(timestamp=time.time())

        # Process metrics (best-effort via psutil or /proc)
        self._collect_process_metrics(snap)

        # Connection metrics
        snap.ws_agent_count = len(self._ctrl.agent_servers)
        snap.nats_agent_count = len(self._ctrl.nats_agents)
        snap.admin_client_count = len(self._ctrl.admin_clients)
        snap.active_session_count = len(self._ctrl.active_sessions)
        snap.active_block_count = len(self._ctrl.active_blocks)

        # Health metrics
        if self._ctrl._health_monitor:
            snap.healthy_agent_count = self._ctrl._health_monitor.get_healthy_count()
            snap.unhealthy_agent_count = (
                self._ctrl._health_monitor.total_agents - snap.healthy_agent_count
            )

        # Log pipeline metrics
        buf_stats = self._ctrl._log_buffer_manager.get_buffer_stats()
        snap.buffered_log_lines = sum(
            s["buffered_lines"] for s in buf_stats.values()
        )
        snap.total_analyses = sum(
            len(v) for v in self._ctrl._analysis_history.values()
        )

        return snap

    def _collect_process_metrics(self, snap: MetricsSnapshot) -> None:
        """Collect process-level metrics using psutil or /proc fallback."""
        try:
            if self._process is None:
                try:
                    import psutil
                    self._process = psutil.Process()
                except ImportError:
                    self._process = "unavailable"

            if self._process == "unavailable":
                self._collect_from_proc(snap)
                return

            snap.cpu_percent = self._process.cpu_percent()
            mem = self._process.memory_info()
            snap.memory_rss_mb = mem.rss / (1024 * 1024)
            snap.memory_vms_mb = mem.vms / (1024 * 1024)

            try:
                snap.open_fds = self._process.num_fds()
            except (AttributeError, OSError):
                snap.open_fds = 0

        except Exception:
            # Silently ignore process metric failures
            pass

    def _collect_from_proc(self, snap: MetricsSnapshot) -> None:
        """/proc fallback for Linux when psutil is unavailable."""
        try:
            pid = os.getpid()
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        snap.memory_rss_mb = int(line.split()[1]) / 1024
                    elif line.startswith("VmSize:"):
                        snap.memory_vms_mb = int(line.split()[1]) / 1024

            # Count open file descriptors
            try:
                snap.open_fds = len(os.listdir(f"/proc/{pid}/fd"))
            except OSError:
                pass
        except (OSError, ValueError):
            pass
