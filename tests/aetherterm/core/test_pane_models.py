"""Tests for core/pane/models — PaneStatus, PaneInfo, PaneConfig."""

from aetherterm.core.pane.models import PaneConfig, PaneInfo, PaneStatus


class TestPaneStatus:
    def test_values(self):
        assert PaneStatus.RUNNING == "running"
        assert PaneStatus.EXITED == "exited"
        assert PaneStatus.BLOCKED == "blocked"


class TestPaneConfig:
    def test_defaults(self):
        c = PaneConfig()
        assert c.cmd == ["/bin/bash"]
        assert c.env == {}
        assert c.cwd is None
        assert c.cols == 80
        assert c.rows == 24
        assert c.role == ""
        assert c.title == ""


class TestPaneInfo:
    def test_auto_id(self):
        p = PaneInfo()
        assert p.pane_id.startswith("pane_")

    def test_explicit_id(self):
        p = PaneInfo(pane_id="my_pane")
        assert p.pane_id == "my_pane"

    def test_to_dict(self):
        config = PaneConfig(role="coder", title="Main", cols=120, rows=40)
        p = PaneInfo(pane_id="p1", config=config, status=PaneStatus.RUNNING)
        d = p.to_dict()
        assert d["pane_id"] == "p1"
        assert d["status"] == "running"
        assert d["role"] == "coder"
        assert d["title"] == "Main"
        assert d["cols"] == 120
        assert d["rows"] == 40
        assert d["exit_code"] is None

    def test_default_status(self):
        p = PaneInfo()
        assert p.status == PaneStatus.RUNNING
