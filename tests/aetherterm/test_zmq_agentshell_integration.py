"""
AgentShell ↔ Broker ↔ AgentServer ZMQ integration tests.

Tests that AgentShell can register with the Broker, send messages,
and have them routed to AgentServer (and vice versa).
"""

import asyncio
import socket

import pytest

from aetherterm.common.agent_protocol import AgentMessage, MessageType
from aetherterm.common.zmq.zmq_broker import ZMQBroker
from aetherterm.common.zmq.zmq_client import ZMQAgentClient
from aetherterm.common.zmq.zmq_config import ZMQConfig


def _get_free_ports(count: int = 3) -> list:
    ports = []
    socks = []
    for _ in range(count):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        ports.append(s.getsockname()[1])
        socks.append(s)
    for s in socks:
        s.close()
    return ports


def _make_config(ports: list) -> ZMQConfig:
    return ZMQConfig(
        enabled=True,
        broker_router_endpoint=f"tcp://127.0.0.1:{ports[0]}",
        broker_pub_endpoint=f"tcp://127.0.0.1:{ports[1]}",
        broker_push_endpoint=f"tcp://127.0.0.1:{ports[2]}",
        heartbeat_interval=2,
        heartbeat_timeout=6,
    )


@pytest.fixture
async def zmq_env():
    """Create Broker + AgentServer client + AgentShell client."""
    ports = _get_free_ports(3)
    config = _make_config(ports)

    broker = ZMQBroker(config)
    await broker.start()

    server_client = ZMQAgentClient(
        agent_id="agentserver",
        config=config,
        capabilities=["hub", "terminal_server"],
    )
    await server_client.connect()
    await server_client.start_recv_loop()
    await server_client.register()

    shell_client = ZMQAgentClient(
        agent_id="agentshell-001",
        config=config,
        capabilities=["pty_middleware", "command_intercept"],
    )
    await shell_client.connect()
    await shell_client.start_recv_loop()
    await shell_client.register()

    await asyncio.sleep(0.2)  # Let registration propagate

    yield broker, server_client, shell_client

    await shell_client.disconnect()
    await server_client.disconnect()
    await broker.stop()


class TestAgentShellRegistration:
    """Test AgentShell registration and discovery via Broker."""

    @pytest.mark.asyncio
    async def test_both_agents_registered(self, zmq_env):
        broker, server_client, shell_client = zmq_env
        assert broker.agent_count == 2
        assert broker.get_agent("agentserver") is not None
        assert broker.get_agent("agentshell-001") is not None

    @pytest.mark.asyncio
    async def test_shell_capabilities(self, zmq_env):
        broker, _, _ = zmq_env
        shell = broker.get_agent("agentshell-001")
        assert "pty_middleware" in shell.capabilities
        assert "command_intercept" in shell.capabilities


class TestAgentShellToServer:
    """Test message routing from AgentShell → AgentServer."""

    @pytest.mark.asyncio
    async def test_shell_sends_command_to_server(self, zmq_env):
        broker, server_client, shell_client = zmq_env

        received = []
        server_client.register_handler(
            MessageType.COMMAND_INJECT,
            lambda msg: received.append(msg),
        )

        msg = AgentMessage(
            from_agent="agentshell-001",
            to_agent="agentserver",
            message_type=MessageType.COMMAND_INJECT,
            payload={"pane_id": "pane-001", "data": "echo hello"},
        )
        await shell_client.send_message(msg)
        await asyncio.sleep(0.3)

        assert len(received) == 1
        assert received[0].payload["data"] == "echo hello"

    @pytest.mark.asyncio
    async def test_shell_sends_intervention_request(self, zmq_env):
        broker, server_client, shell_client = zmq_env

        received = []
        server_client.register_handler(
            MessageType.INTERVENTION_REQUEST,
            lambda msg: received.append(msg),
        )

        msg = AgentMessage(
            from_agent="agentshell-001",
            to_agent="agentserver",
            message_type=MessageType.INTERVENTION_REQUEST,
            payload={
                "session_id": "sess-001",
                "threat_level": "high",
                "message": "rm -rf detected",
            },
        )
        await shell_client.send_message(msg)
        await asyncio.sleep(0.3)

        assert len(received) == 1
        assert received[0].payload["threat_level"] == "high"


class TestServerToAgentShell:
    """Test message routing from AgentServer → AgentShell."""

    @pytest.mark.asyncio
    async def test_server_sends_block_to_shell(self, zmq_env):
        broker, server_client, shell_client = zmq_env

        received = []
        shell_client.register_handler(
            MessageType.INPUT_BLOCK,
            lambda msg: received.append(msg),
        )

        msg = AgentMessage(
            from_agent="agentserver",
            to_agent="agentshell-001",
            message_type=MessageType.INPUT_BLOCK,
            payload={"pane_id": "pane-001", "reason": "admin block"},
        )
        await server_client.send_message(msg)
        await asyncio.sleep(0.3)

        assert len(received) == 1
        assert received[0].payload["reason"] == "admin block"
