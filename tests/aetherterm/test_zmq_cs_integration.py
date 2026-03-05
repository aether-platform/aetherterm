"""
AgentServer ↔ Broker ↔ ControlServer ZMQ integration tests.

Tests that ControlServer can register with the Broker, receive session updates,
and send emergency block commands through the Broker.
"""

import asyncio
import socket

import pytest

from aetherterm.common.agent_protocol import AgentMessage, MessageType
from aetherterm.common.zmq.zmq_broker import ZMQBroker
from aetherterm.common.zmq.zmq_client import ZMQAgentClient
from aetherterm.common.zmq.zmq_config import ZMQConfig
from aetherterm.controlserver.zmq_controller import ControlServerZMQ


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
        cs_enabled=True,
        broker_router_endpoint=f"tcp://127.0.0.1:{ports[0]}",
        broker_pub_endpoint=f"tcp://127.0.0.1:{ports[1]}",
        broker_push_endpoint=f"tcp://127.0.0.1:{ports[2]}",
        heartbeat_interval=2,
        heartbeat_timeout=6,
    )


@pytest.fixture
async def cs_zmq_env():
    """Create Broker + AgentServer client + ControlServer ZMQ transport."""
    ports = _get_free_ports(3)
    config = _make_config(ports)

    broker = ZMQBroker(config)
    await broker.start()

    # AgentServer client
    server_client = ZMQAgentClient(
        agent_id="agentserver",
        config=config,
        capabilities=["hub", "terminal_server"],
    )
    await server_client.connect()
    await server_client.start_recv_loop()
    await server_client.register()

    # ControlServer ZMQ transport
    cs_received = []

    async def on_cs_message(msg):
        cs_received.append(msg)

    cs_zmq = ControlServerZMQ(
        zmq_config=config,
        on_agent_message=on_cs_message,
    )
    await cs_zmq.start()

    await asyncio.sleep(0.3)

    yield broker, server_client, cs_zmq, cs_received

    await cs_zmq.stop()
    await server_client.disconnect()
    await broker.stop()


class TestControlServerRegistration:
    """Test ControlServer registration via Broker."""

    @pytest.mark.asyncio
    async def test_controlserver_registered(self, cs_zmq_env):
        broker, _, cs_zmq, _ = cs_zmq_env
        assert broker.get_agent("controlserver") is not None
        assert cs_zmq.is_connected

    @pytest.mark.asyncio
    async def test_both_agents_registered(self, cs_zmq_env):
        broker, _, _, _ = cs_zmq_env
        assert broker.agent_count == 2


class TestAgentServerToControlServer:
    """Test AgentServer → ControlServer message routing."""

    @pytest.mark.asyncio
    async def test_session_update(self, cs_zmq_env):
        broker, server_client, cs_zmq, cs_received = cs_zmq_env

        msg = AgentMessage(
            from_agent="agentserver",
            to_agent="controlserver",
            message_type=MessageType.SESSION_UPDATE,
            payload={
                "session": {
                    "session_id": "sess-001",
                    "user_info": {"username": "test"},
                },
            },
        )
        await server_client.send_message(msg)
        await asyncio.sleep(0.3)

        assert len(cs_received) >= 1
        session_updates = [
            m for m in cs_received
            if m.message_type == MessageType.SESSION_UPDATE
        ]
        assert len(session_updates) == 1
        assert session_updates[0].payload["session"]["session_id"] == "sess-001"

    @pytest.mark.asyncio
    async def test_block_confirmation(self, cs_zmq_env):
        broker, server_client, cs_zmq, cs_received = cs_zmq_env

        msg = AgentMessage(
            from_agent="agentserver",
            to_agent="controlserver",
            message_type=MessageType.BLOCK_CONFIRMATION,
            payload={
                "block_id": "blk-001",
                "confirmed_sessions": ["sess-001", "sess-002"],
            },
        )
        await server_client.send_message(msg)
        await asyncio.sleep(0.3)

        confirmations = [
            m for m in cs_received
            if m.message_type == MessageType.BLOCK_CONFIRMATION
        ]
        assert len(confirmations) == 1
        assert confirmations[0].payload["block_id"] == "blk-001"


class TestControlServerToAgentServer:
    """Test ControlServer → AgentServer message routing."""

    @pytest.mark.asyncio
    async def test_emergency_block(self, cs_zmq_env):
        broker, server_client, cs_zmq, _ = cs_zmq_env

        received = []
        server_client.register_handler(
            MessageType.EMERGENCY_BLOCK,
            lambda msg: received.append(msg),
        )

        await cs_zmq.send_to_agent(
            "agentserver",
            AgentMessage(
                from_agent="controlserver",
                to_agent="agentserver",
                message_type=MessageType.EMERGENCY_BLOCK,
                payload={
                    "block_id": "blk-emergency",
                    "severity": "admin_initiated",
                    "message": "Emergency block test",
                    "affected_sessions": ["sess-001"],
                },
            ),
        )
        await asyncio.sleep(0.3)

        assert len(received) == 1
        assert received[0].payload["block_id"] == "blk-emergency"

    @pytest.mark.asyncio
    async def test_unblock_session(self, cs_zmq_env):
        broker, server_client, cs_zmq, _ = cs_zmq_env

        received = []
        server_client.register_handler(
            MessageType.UNBLOCK_SESSION,
            lambda msg: received.append(msg),
        )

        await cs_zmq.send_unblock("agentserver", "sess-001", "admin")
        await asyncio.sleep(0.3)

        assert len(received) == 1
        assert received[0].payload["session_id"] == "sess-001"
