"""Tests for ControlServer HealthMonitor and MetricsCollector."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aetherterm.controlserver.health_monitor import AgentHealth, HealthMonitor
from aetherterm.controlserver.metrics_collector import MetricsCollector, MetricsSnapshot


# ---------------------------------------------------------------------------
# AgentHealth unit tests
# ---------------------------------------------------------------------------


class TestAgentHealth:
    def test_init(self):
        h = AgentHealth("agent-1", "nats")
        assert h.agent_id == "agent-1"
        assert h.transport == "nats"
        assert h.is_healthy is True
        assert h.missed_count == 0

    def test_record_heartbeat_healthy(self):
        h = AgentHealth("agent-1")
        recovered = h.record_heartbeat()
        assert recovered is False  # was already healthy

    def test_record_heartbeat_recovery(self):
        h = AgentHealth("agent-1")
        h.is_healthy = False
        h.missed_count = 3
        recovered = h.record_heartbeat()
        assert recovered is True
        assert h.is_healthy is True
        assert h.missed_count == 0

    def test_check_healthy(self):
        h = AgentHealth("agent-1")
        assert h.check(timeout=60.0) is True
        assert h.is_healthy is True

    def test_check_stale(self):
        h = AgentHealth("agent-1")
        h.last_heartbeat = time.time() - 120  # 2 min ago
        assert h.check(timeout=60.0) is False
        assert h.is_healthy is False
        assert h.missed_count == 1

    def test_to_dict(self):
        h = AgentHealth("agent-1", "websocket")
        d = h.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["transport"] == "websocket"
        assert d["is_healthy"] is True
        assert "last_heartbeat_ago_sec" in d
        assert "uptime_sec" in d


# ---------------------------------------------------------------------------
# HealthMonitor unit tests
# ---------------------------------------------------------------------------


def _make_mock_controller():
    ctrl = MagicMock()
    ctrl.agent_servers = {}
    ctrl.nats_agents = {}
    ctrl.admin_clients = set()
    ctrl.active_sessions = {}
    ctrl.active_blocks = {}
    ctrl._nats_controller = None
    ctrl._health_monitor = None
    ctrl._metrics_collector = None
    ctrl._log_buffer_manager = MagicMock()
    ctrl._log_buffer_manager.get_buffer_stats.return_value = {}
    ctrl._analysis_history = {}
    ctrl.broadcast_to_admins = AsyncMock()
    return ctrl


class TestHealthMonitor:
    def test_register_and_heartbeat(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)

        hm.register_agent("agent-1", "nats")
        assert hm.total_agents == 1
        assert hm.get_healthy_count() == 1

        hm.record_heartbeat("agent-1")
        assert hm.get_healthy_count() == 1

    def test_register_unknown_via_heartbeat(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)

        hm.record_heartbeat("agent-new")
        assert hm.total_agents == 1

    def test_unregister(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)
        hm.register_agent("agent-1")
        hm.unregister_agent("agent-1")
        assert hm.total_agents == 0

    def test_get_health(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)
        hm.register_agent("agent-1")
        health = hm.get_health("agent-1")
        assert health is not None
        assert health["agent_id"] == "agent-1"

    def test_get_health_missing(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)
        assert hm.get_health("nonexistent") is None

    def test_get_all_health(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl)
        hm.register_agent("agent-1")
        hm.register_agent("agent-2")
        all_health = hm.get_all_health()
        assert len(all_health) == 2

    def test_unhealthy_detection(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl, heartbeat_timeout=1.0)
        hm.register_agent("agent-1")
        # Simulate stale heartbeat
        hm._agents["agent-1"].last_heartbeat = time.time() - 10
        assert hm.get_unhealthy_agents() == []  # Not checked yet
        hm._agents["agent-1"].check(1.0)
        assert hm.get_unhealthy_agents() == ["agent-1"]

    @pytest.mark.asyncio
    async def test_check_agents_detects_unhealthy(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl, heartbeat_timeout=1.0, stale_removal=5.0)
        hm.register_agent("agent-1")
        hm._agents["agent-1"].last_heartbeat = time.time() - 10

        await hm._check_agents()
        assert ctrl.broadcast_to_admins.called

    @pytest.mark.asyncio
    async def test_check_agents_removes_stale(self):
        ctrl = _make_mock_controller()
        hm = HealthMonitor(ctrl, heartbeat_timeout=1.0, stale_removal=2.0)
        hm.register_agent("agent-1")
        hm._agents["agent-1"].last_heartbeat = time.time() - 10
        hm._agents["agent-1"].is_healthy = False

        await hm._check_agents()
        assert hm.total_agents == 0


# ---------------------------------------------------------------------------
# MetricsSnapshot tests
# ---------------------------------------------------------------------------


class TestMetricsSnapshot:
    def test_to_dict(self):
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_percent=15.0,
            memory_rss_mb=128.5,
            ws_agent_count=2,
            nats_agent_count=3,
            active_session_count=5,
        )
        d = snap.to_dict()
        assert d["process"]["cpu_percent"] == 15.0
        assert d["connections"]["ws_agents"] == 2
        assert d["connections"]["nats_agents"] == 3
        assert d["connections"]["active_sessions"] == 5


# ---------------------------------------------------------------------------
# MetricsCollector unit tests
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    def test_collect_now(self):
        ctrl = _make_mock_controller()
        ctrl._health_monitor = HealthMonitor(ctrl)
        mc = MetricsCollector(ctrl)

        snap = mc.collect_now()
        assert isinstance(snap, MetricsSnapshot)
        assert snap.timestamp > 0

    def test_get_latest_empty(self):
        ctrl = _make_mock_controller()
        mc = MetricsCollector(ctrl)
        assert mc.get_latest() is None

    def test_get_history(self):
        ctrl = _make_mock_controller()
        ctrl._health_monitor = HealthMonitor(ctrl)
        mc = MetricsCollector(ctrl)

        # Manually add snapshots
        mc._history.append(mc.collect_now())
        mc._history.append(mc.collect_now())
        assert len(mc.get_history()) == 2

    def test_get_latest(self):
        ctrl = _make_mock_controller()
        ctrl._health_monitor = HealthMonitor(ctrl)
        mc = MetricsCollector(ctrl)

        mc._history.append(mc.collect_now())
        latest = mc.get_latest()
        assert latest is not None
        assert "process" in latest
        assert "connections" in latest
