"""
Tests for AgentPaneManager and MessageRouter.

These tests validate pane CRUD operations, message routing,
callback registration, and socket mappings without requiring
a real terminal (AsyncioTerminal is mocked).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aetherterm.agentserver.agent_pane_manager import (
    AgentPane,
    AgentPaneManager,
    MessageRouter,
)
from aetherterm.common.agent_protocol import (
    AgentMessage,
    MessageType,
    PaneConfig,
    PaneType,
)


@pytest.fixture
def broadcast_fn():
    return MagicMock()


@pytest.fixture
def pane_manager(broadcast_fn):
    return AgentPaneManager(broadcast_fn=broadcast_fn)


@pytest.fixture
def pane_config():
    return PaneConfig(
        pane_type=PaneType.TERMINAL,
        title="Test Terminal",
        size={"rows": 24, "cols": 80},
    )


@pytest.fixture
def agent_pane_config():
    return PaneConfig(
        pane_type=PaneType.AGENT,
        title="Test Agent",
        size={"rows": 24, "cols": 80},
        agent_config={"auto_start": False},
    )


# --- AgentPane dataclass tests ---


class TestAgentPane:
    def test_to_dict(self):
        pane = AgentPane(
            pane_id="pane_123",
            parent_session_id="session_1",
            agent_id="agent_1",
            agent_type="test",
            pane_type=PaneType.TERMINAL,
            title="Test",
        )
        d = pane.to_dict()
        assert d["pane_id"] == "pane_123"
        assert d["parent_session_id"] == "session_1"
        assert d["agent_id"] == "agent_1"
        assert d["pane_type"] == "terminal"
        assert d["title"] == "Test"
        assert d["status"] == "active"

    def test_default_values(self):
        pane = AgentPane()
        assert pane.pane_id.startswith("pane_")
        assert pane.status == "active"
        assert pane.terminal_id is None
        assert pane.socket_id is None
        assert pane.config == {}
        assert pane.metadata == {}


# --- AgentPaneManager tests ---


class TestAgentPaneManager:
    @pytest.mark.asyncio
    @patch(
        "aetherterm.agentserver.agent_pane_manager.AgentPaneManager._create_terminal_session",
        new_callable=AsyncMock,
        return_value="term_mock123",
    )
    async def test_create_pane(self, mock_create, pane_manager, pane_config):
        # Enable terminal creation
        pane_manager.set_terminal_manager(MagicMock())

        pane = await pane_manager.create_agent_pane(
            parent_session_id="session_1",
            agent_type="shell",
            config=pane_config,
        )

        assert pane.pane_id in pane_manager._panes
        assert pane.parent_session_id == "session_1"
        assert pane.agent_type == "shell"
        assert pane.title == "Test Terminal"
        assert pane.terminal_id == "term_mock123"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pane_without_terminal_manager(self, pane_manager, pane_config):
        """When no terminal_manager is set, no terminal session is created."""
        pane = await pane_manager.create_agent_pane(
            parent_session_id="session_1",
            agent_type="shell",
            config=pane_config,
        )

        assert pane.terminal_id is None
        assert pane.pane_id in pane_manager._panes

    @pytest.mark.asyncio
    @patch(
        "aetherterm.agentserver.agent_pane_manager.AgentPaneManager._create_terminal_session",
        new_callable=AsyncMock,
        return_value="term_mock1",
    )
    async def test_destroy_pane(self, mock_create, pane_manager, pane_config):
        pane_manager.set_terminal_manager(MagicMock())

        pane = await pane_manager.create_agent_pane(
            parent_session_id="session_1",
            agent_type="shell",
            config=pane_config,
        )
        pane_id = pane.pane_id

        with patch.object(
            pane_manager, "_destroy_terminal_session", new_callable=AsyncMock
        ) as mock_destroy:
            result = await pane_manager.destroy_pane(pane_id)

        assert result is True
        assert pane_id not in pane_manager._panes
        mock_destroy.assert_called_once_with("term_mock1")

    @pytest.mark.asyncio
    async def test_destroy_nonexistent_pane(self, pane_manager):
        result = await pane_manager.destroy_pane("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_panes(self, pane_manager, pane_config):
        pane1 = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        pane2 = await pane_manager.create_agent_pane("sess2", "openhands", pane_config)

        # All panes
        all_panes = pane_manager.list_panes()
        assert len(all_panes) == 2

        # Filter by session
        session_panes = pane_manager.list_panes(parent_session_id="sess1")
        assert len(session_panes) == 1
        assert session_panes[0].pane_id == pane1.pane_id

        # Filter by agent type
        agent_panes = pane_manager.list_panes(agent_type="openhands")
        assert len(agent_panes) == 1
        assert agent_panes[0].pane_id == pane2.pane_id

    @pytest.mark.asyncio
    async def test_get_pane(self, pane_manager, pane_config):
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)

        found = pane_manager.get_pane(pane.pane_id)
        assert found is not None
        assert found.pane_id == pane.pane_id

        not_found = pane_manager.get_pane("nonexistent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_get_pane_by_agent(self, pane_manager, pane_config):
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)

        found = pane_manager.get_pane_by_agent(pane.agent_id)
        assert found is not None
        assert found.pane_id == pane.pane_id

        not_found = pane_manager.get_pane_by_agent("nonexistent_agent")
        assert not_found is None

    def test_update_socket_mapping(self, pane_manager):
        pane = AgentPane(pane_id="pane_test", agent_id="agent_test")
        pane_manager._panes["pane_test"] = pane

        pane_manager.update_socket_mapping("pane_test", "socket_abc")
        assert pane.socket_id == "socket_abc"
        assert pane_manager._socket_to_pane["socket_abc"] == "pane_test"

        found = pane_manager.get_pane_by_socket("socket_abc")
        assert found is not None
        assert found.pane_id == "pane_test"

    def test_update_socket_mapping_replaces_old(self, pane_manager):
        pane = AgentPane(pane_id="pane_test", agent_id="agent_test", socket_id="old_socket")
        pane_manager._panes["pane_test"] = pane
        pane_manager._socket_to_pane["old_socket"] = "pane_test"

        pane_manager.update_socket_mapping("pane_test", "new_socket")

        assert "old_socket" not in pane_manager._socket_to_pane
        assert pane_manager._socket_to_pane["new_socket"] == "pane_test"
        assert pane.socket_id == "new_socket"

    @pytest.mark.asyncio
    async def test_pane_created_callback(self, pane_manager, pane_config):
        callback = MagicMock()
        pane_manager.register_pane_created_callback(callback)

        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        callback.assert_called_once_with(pane)

    @pytest.mark.asyncio
    async def test_pane_destroyed_callback(self, pane_manager, pane_config):
        callback = MagicMock()
        pane_manager.register_pane_destroyed_callback(callback)

        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        pane_id = pane.pane_id

        await pane_manager.destroy_pane(pane_id)
        callback.assert_called_once_with(pane_id)

    def test_set_broadcast_fn(self, pane_manager):
        new_fn = MagicMock()
        pane_manager.set_broadcast_fn(new_fn)
        assert pane_manager._broadcast_fn is new_fn

    def test_unregister_callbacks(self, pane_manager):
        cb1 = MagicMock()
        pane_manager.register_pane_created_callback(cb1)
        assert cb1 in pane_manager._pane_created_callbacks

        pane_manager.unregister_pane_created_callback(cb1)
        assert cb1 not in pane_manager._pane_created_callbacks

    @pytest.mark.asyncio
    async def test_filter_panes_by_status(self, pane_manager, pane_config):
        pane1 = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        pane2 = await pane_manager.create_agent_pane("sess1", "monitor", pane_config)

        # Mark one as stopped
        pane2.status = "stopped"

        active_panes = pane_manager.list_panes(status="active")
        assert len(active_panes) == 1
        assert active_panes[0].pane_id == pane1.pane_id

        stopped_panes = pane_manager.list_panes(status="stopped")
        assert len(stopped_panes) == 1
        assert stopped_panes[0].pane_id == pane2.pane_id


# --- MessageRouter tests ---


class TestMessageRouter:
    @pytest.fixture
    def router(self, pane_manager):
        router = MessageRouter(pane_manager)
        pane_manager.set_message_router(router)
        return router

    @pytest.mark.asyncio
    async def test_route_to_existing_pane(self, pane_manager, router, pane_config):
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)

        handler = AsyncMock()
        router.register_handler(pane.pane_id, handler)

        message = AgentMessage(
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls -la"},
        )

        result = await router.route("system", pane.pane_id, message)
        assert result is True
        handler.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_route_to_nonexistent_pane(self, router):
        message = AgentMessage(
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls"},
        )

        result = await router.route("system", "nonexistent", message)
        assert result is False

    @pytest.mark.asyncio
    async def test_route_by_agent_id(self, pane_manager, router, pane_config):
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)

        handler = AsyncMock()
        router.register_handler(pane.pane_id, handler)

        message = AgentMessage(
            message_type=MessageType.COMMAND_PROPOSE,
            payload={"command": "echo hello"},
        )

        result = await router.route("system", pane.agent_id, message)
        assert result is True
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_without_handler(self, pane_manager, router, pane_config):
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)

        message = AgentMessage(
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls"},
        )

        # No handler registered — default routing returns True
        result = await router.route("system", pane.pane_id, message)
        assert result is True

    def test_unregister_handler(self, router):
        handler = AsyncMock()
        router.register_handler("pane_1", handler)
        assert "pane_1" in router._handlers

        router.unregister_handler("pane_1")
        assert "pane_1" not in router._handlers

    @pytest.mark.asyncio
    async def test_broadcast_to_agents(self, pane_manager, router, pane_config):
        pane1 = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        pane2 = await pane_manager.create_agent_pane("sess1", "monitor", pane_config)

        message = AgentMessage(
            message_type=MessageType.COMMAND_PROPOSE,
            payload={"command": "uptime"},
        )

        # Broadcast to all
        count = await pane_manager.broadcast_to_agents(message)
        assert count == 2

        # Broadcast filtered by agent type
        count = await pane_manager.broadcast_to_agents(message, agent_types=["shell"])
        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_skips_inactive(self, pane_manager, router, pane_config):
        pane1 = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        pane2 = await pane_manager.create_agent_pane("sess1", "monitor", pane_config)
        pane2.status = "stopped"

        message = AgentMessage(
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls"},
        )

        count = await pane_manager.broadcast_to_agents(message)
        assert count == 1


# --- Integration tests ---


class TestPaneManagerIntegration:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, pane_manager, pane_config):
        """Test create → update → route → destroy lifecycle."""
        router = MessageRouter(pane_manager)
        pane_manager.set_message_router(router)

        # Create
        pane = await pane_manager.create_agent_pane("sess1", "shell", pane_config)
        assert pane_manager.get_pane(pane.pane_id) is not None

        # Socket mapping
        pane_manager.update_socket_mapping(pane.pane_id, "socket_xyz")
        assert pane_manager.get_pane_by_socket("socket_xyz") is not None

        # Route a message
        handler = AsyncMock()
        router.register_handler(pane.pane_id, handler)

        msg = AgentMessage(
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "whoami"},
        )
        result = await pane_manager.route_message("system", pane.pane_id, msg)
        assert result is True
        handler.assert_called_once()

        # Destroy
        result = await pane_manager.destroy_pane(pane.pane_id)
        assert result is True
        assert pane_manager.get_pane(pane.pane_id) is None
        assert pane_manager.get_pane_by_socket("socket_xyz") is None

    @pytest.mark.asyncio
    async def test_multiple_panes_different_sessions(self, pane_manager, pane_config):
        """Multiple panes across different sessions."""
        p1 = await pane_manager.create_agent_pane("sess_a", "shell", pane_config)
        p2 = await pane_manager.create_agent_pane("sess_b", "shell", pane_config)
        p3 = await pane_manager.create_agent_pane("sess_a", "monitor", pane_config)

        assert len(pane_manager.list_panes()) == 3
        assert len(pane_manager.list_panes(parent_session_id="sess_a")) == 2
        assert len(pane_manager.list_panes(parent_session_id="sess_b")) == 1
        assert len(pane_manager.list_panes(agent_type="monitor")) == 1
