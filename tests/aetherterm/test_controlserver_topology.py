"""Tests for ControlServer topology API."""

from unittest.mock import MagicMock

import pytest

from aetherterm.common.models import PaneDetail, PtySessionInfo, WindowDetail
from aetherterm.controlserver.rest_api import _build_topology, _build_topology_flat


def _mock_controller(sessions=None, health_agents=None):
    """Create a mock controller with optional sessions and health data."""
    ctrl = MagicMock()
    ctrl.agent_servers = {}
    ctrl.nats_agents = {}
    ctrl.active_sessions = {}
    ctrl.active_blocks = {}

    # NATS controller
    if sessions is not None:
        nats = MagicMock()
        nats.list_sessions.return_value = sessions
        ctrl._nats_controller = nats
    else:
        ctrl._nats_controller = None

    # Health monitor
    if health_agents is not None:
        hm = MagicMock()
        hm.get_all_health.return_value = health_agents
        hm.get_health.side_effect = lambda aid: next(
            (h for h in health_agents if h["agent_id"] == aid), None
        )
        ctrl._health_monitor = hm
    else:
        ctrl._health_monitor = None

    return ctrl


def _make_session(
    session_id, agent_id, user_id="unknown", name="", panes=None
):
    """Helper to build a PtySessionInfo with window/pane details."""
    pane_details = []
    pane_ids = []
    for p in (panes or []):
        pane_details.append(
            PaneDetail(
                pane_id=p["pane_id"],
                status=p.get("status", "running"),
                role=p.get("role", ""),
            )
        )
        pane_ids.append(p["pane_id"])

    windows = []
    if pane_details:
        windows.append(
            WindowDetail(
                window_id=f"win_{session_id[:4]}",
                name=name or "main",
                panes=pane_details,
            )
        )

    return PtySessionInfo(
        session_id=session_id,
        agent_server_id=agent_id,
        name=name,
        user_info={"user_id": user_id} if user_id != "unknown" else {},
        pane_ids=pane_ids,
        windows=windows,
    )


class TestBuildTopology:
    def test_empty(self):
        ctrl = _mock_controller()
        assert _build_topology(ctrl) == []

    def test_single_agent_single_user(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "main", [
                {"pane_id": "p1", "status": "running", "role": "coder"},
                {"pane_id": "p2", "status": "running", "role": "reviewer"},
            ])
        ]
        ctrl = _mock_controller(sessions)
        tree = _build_topology(ctrl)

        assert len(tree) == 1
        agent = tree[0]
        assert agent["agent_server_id"] == "agent-1"
        assert agent["user_count"] == 1
        assert agent["session_count"] == 1
        assert agent["pane_count"] == 2

        user = agent["users"][0]
        assert user["user_id"] == "alice"
        assert user["session_count"] == 1
        assert user["pane_count"] == 2

        sess = user["sessions"][0]
        assert sess["session_id"] == "s1"
        assert len(sess["panes"]) == 2
        assert sess["panes"][0]["pane_id"] == "p1"
        assert sess["panes"][0]["role"] == "coder"

    def test_multiple_users_on_same_agent(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "dev", [
                {"pane_id": "p1"},
            ]),
            _make_session("s2", "agent-1", "bob", "test", [
                {"pane_id": "p2"},
                {"pane_id": "p3"},
            ]),
        ]
        ctrl = _mock_controller(sessions)
        tree = _build_topology(ctrl)

        assert len(tree) == 1
        agent = tree[0]
        assert agent["user_count"] == 2
        assert agent["pane_count"] == 3

        user_ids = [u["user_id"] for u in agent["users"]]
        assert "alice" in user_ids
        assert "bob" in user_ids

    def test_multiple_agents(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "", [{"pane_id": "p1"}]),
            _make_session("s2", "agent-2", "bob", "", [{"pane_id": "p2"}]),
        ]
        ctrl = _mock_controller(sessions)
        tree = _build_topology(ctrl)

        assert len(tree) == 2
        agent_ids = [a["agent_server_id"] for a in tree]
        assert "agent-1" in agent_ids
        assert "agent-2" in agent_ids

    def test_health_included(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "", [{"pane_id": "p1"}]),
        ]
        health = [{"agent_id": "agent-1", "is_healthy": True}]
        ctrl = _mock_controller(sessions, health)
        tree = _build_topology(ctrl)

        assert tree[0]["health"]["is_healthy"] is True

    def test_agent_without_sessions_from_health(self):
        """Agents with no sessions should still appear if health monitor tracks them."""
        health = [
            {"agent_id": "agent-empty", "is_healthy": True},
        ]
        ctrl = _mock_controller(sessions=[], health_agents=health)
        tree = _build_topology(ctrl)

        assert len(tree) == 1
        assert tree[0]["agent_server_id"] == "agent-empty"
        assert tree[0]["user_count"] == 0

    def test_blocked_session(self):
        from aetherterm.common.models import BlockCommand
        sessions = [
            _make_session("s1", "agent-1", "alice", "", [{"pane_id": "p1"}]),
        ]
        ctrl = _mock_controller(sessions)
        # Add active block
        ctrl.active_blocks = {
            "b1": BlockCommand(
                block_id="b1",
                block_type="admin_initiated",
                reason="Test block",
                affected_sessions=["s1"],
            )
        }
        tree = _build_topology(ctrl)
        sess = tree[0]["users"][0]["sessions"][0]
        assert sess["is_blocked"] is True
        assert sess["block_reason"] == "Test block"


class TestBuildTopologyFlat:
    def test_empty(self):
        ctrl = _mock_controller()
        assert _build_topology_flat(ctrl) == []

    def test_basic_flat(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "main", [
                {"pane_id": "p1", "status": "running", "role": "coder"},
                {"pane_id": "p2", "status": "blocked", "role": "reviewer"},
            ]),
        ]
        ctrl = _mock_controller(sessions)
        flat = _build_topology_flat(ctrl)

        assert len(flat) == 2

        row1 = flat[0]
        assert row1["agent_server_id"] == "agent-1"
        assert row1["user_id"] == "alice"
        assert row1["session_id"] == "s1"
        assert row1["pane_id"] == "p1"
        assert row1["pane_status"] == "running"
        assert row1["pane_role"] == "coder"

        row2 = flat[1]
        assert row2["pane_id"] == "p2"
        assert row2["pane_status"] == "blocked"

    def test_flat_multiple_agents_and_users(self):
        sessions = [
            _make_session("s1", "agent-1", "alice", "", [{"pane_id": "p1"}]),
            _make_session("s2", "agent-1", "bob", "", [{"pane_id": "p2"}]),
            _make_session("s3", "agent-2", "carol", "", [
                {"pane_id": "p3"},
                {"pane_id": "p4"},
            ]),
        ]
        ctrl = _mock_controller(sessions)
        flat = _build_topology_flat(ctrl)

        assert len(flat) == 4
        agents = {r["agent_server_id"] for r in flat}
        assert agents == {"agent-1", "agent-2"}
        users = {r["user_id"] for r in flat}
        assert users == {"alice", "bob", "carol"}

    def test_session_with_no_panes(self):
        """Session with no panes should still produce a row."""
        sessions = [
            _make_session("s1", "agent-1", "alice", "empty", panes=[]),
        ]
        ctrl = _mock_controller(sessions)
        flat = _build_topology_flat(ctrl)

        assert len(flat) == 1
        assert flat[0]["pane_id"] == ""
        assert flat[0]["session_id"] == "s1"
