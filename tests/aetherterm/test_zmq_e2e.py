"""
Full-chain ZMQ E2E integration tests.

Tests the complete message flow:
  AgentShell → Broker → AgentServer → Broker → ControlServer
  ControlServer → Broker → AgentServer → Broker → AgentShell
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
async def e2e_env():
    """Create full chain: Broker + AgentServer + AgentShell + ControlServer."""
    ports = _get_free_ports(3)
    config = _make_config(ports)

    broker = ZMQBroker(config)
    await broker.start()

    # AgentServer client
    server_client = ZMQAgentClient(
        agent_id="agentserver",
        config=config,
        capabilities=["hub", "terminal_server", "session_manager"],
    )
    await server_client.connect()
    await server_client.start_recv_loop()
    await server_client.register()

    # AgentShell client
    shell_client = ZMQAgentClient(
        agent_id="agentshell-001",
        config=config,
        capabilities=["pty_middleware", "command_intercept"],
    )
    await shell_client.connect()
    await shell_client.start_recv_loop()
    await shell_client.register()

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

    yield broker, server_client, shell_client, cs_zmq, cs_received

    await cs_zmq.stop()
    await shell_client.disconnect()
    await server_client.disconnect()
    await broker.stop()


class TestFullChainRegistration:
    """Verify all 3 components register with the Broker."""

    @pytest.mark.asyncio
    async def test_all_three_registered(self, e2e_env):
        broker, _, _, _, _ = e2e_env
        assert broker.agent_count == 3
        assert broker.get_agent("agentserver") is not None
        assert broker.get_agent("agentshell-001") is not None
        assert broker.get_agent("controlserver") is not None


class TestShellToControlServerViaServer:
    """AgentShell → Broker → AgentServer (relay) → Broker → ControlServer."""

    @pytest.mark.asyncio
    async def test_intervention_reaches_controlserver(self, e2e_env):
        """Shell detects threat → AgentServer receives → forwards to ControlServer."""
        broker, server_client, shell_client, cs_zmq, cs_received = e2e_env

        # AgentServer relays INTERVENTION_REQUEST to ControlServer
        server_relay = []
        server_client.register_handler(
            MessageType.INTERVENTION_REQUEST,
            lambda msg: server_relay.append(msg),
        )

        # Shell sends intervention to AgentServer
        msg = AgentMessage(
            from_agent="agentshell-001",
            to_agent="agentserver",
            message_type=MessageType.INTERVENTION_REQUEST,
            payload={
                "session_id": "sess-e2e",
                "threat_level": "critical",
                "command": "rm -rf /",
                "message": "Dangerous command detected",
            },
        )
        await shell_client.send_message(msg)
        await asyncio.sleep(0.3)

        # AgentServer received
        assert len(server_relay) == 1
        assert server_relay[0].payload["threat_level"] == "critical"

        # AgentServer forwards to ControlServer
        forward_msg = AgentMessage(
            from_agent="agentserver",
            to_agent="controlserver",
            message_type=MessageType.INTERVENTION_REQUEST,
            payload=server_relay[0].payload,
        )
        await server_client.send_message(forward_msg)
        await asyncio.sleep(0.3)

        # ControlServer received
        interventions = [
            m for m in cs_received
            if m.message_type == MessageType.INTERVENTION_REQUEST
        ]
        assert len(interventions) == 1
        assert interventions[0].payload["session_id"] == "sess-e2e"


class TestControlServerToShellViaServer:
    """ControlServer → Broker → AgentServer (relay) → Broker → AgentShell."""

    @pytest.mark.asyncio
    async def test_emergency_block_reaches_shell(self, e2e_env):
        """ControlServer issues emergency block → AgentServer → Shell blocks input."""
        broker, server_client, shell_client, cs_zmq, _ = e2e_env

        # AgentServer relays EMERGENCY_BLOCK to Shell as INPUT_BLOCK
        server_relay = []
        server_client.register_handler(
            MessageType.EMERGENCY_BLOCK,
            lambda msg: server_relay.append(msg),
        )

        shell_blocks = []
        shell_client.register_handler(
            MessageType.INPUT_BLOCK,
            lambda msg: shell_blocks.append(msg),
        )

        # ControlServer sends emergency block to AgentServer
        await cs_zmq.send_to_agent(
            "agentserver",
            AgentMessage(
                from_agent="controlserver",
                to_agent="agentserver",
                message_type=MessageType.EMERGENCY_BLOCK,
                payload={
                    "block_id": "blk-e2e",
                    "severity": "admin_initiated",
                    "message": "Emergency block from control",
                    "affected_sessions": ["sess-e2e"],
                },
            ),
        )
        await asyncio.sleep(0.3)

        # AgentServer received
        assert len(server_relay) == 1
        assert server_relay[0].payload["block_id"] == "blk-e2e"

        # AgentServer forwards block command to Shell
        block_msg = AgentMessage(
            from_agent="agentserver",
            to_agent="agentshell-001",
            message_type=MessageType.INPUT_BLOCK,
            payload={
                "pane_id": "pane-001",
                "reason": server_relay[0].payload["message"],
                "block_id": server_relay[0].payload["block_id"],
            },
        )
        await server_client.send_message(block_msg)
        await asyncio.sleep(0.3)

        # Shell received block
        assert len(shell_blocks) == 1
        assert shell_blocks[0].payload["block_id"] == "blk-e2e"


class TestBidirectionalFlow:
    """Test full request-response cycle across all components."""

    @pytest.mark.asyncio
    async def test_session_update_and_block_response(self, e2e_env):
        """AgentServer reports session → ControlServer responds with block."""
        broker, server_client, shell_client, cs_zmq, cs_received = e2e_env

        # Step 1: AgentServer reports session update to ControlServer
        session_msg = AgentMessage(
            from_agent="agentserver",
            to_agent="controlserver",
            message_type=MessageType.SESSION_UPDATE,
            payload={
                "session": {
                    "session_id": "sess-bidir",
                    "user_info": {"username": "testuser"},
                    "agent_shells": ["agentshell-001"],
                },
            },
        )
        await server_client.send_message(session_msg)
        await asyncio.sleep(0.3)

        # ControlServer received session update
        updates = [
            m for m in cs_received
            if m.message_type == MessageType.SESSION_UPDATE
        ]
        assert len(updates) == 1
        assert updates[0].payload["session"]["session_id"] == "sess-bidir"

        # Step 2: ControlServer decides to block (simulating admin action)
        server_blocks = []
        server_client.register_handler(
            MessageType.EMERGENCY_BLOCK,
            lambda msg: server_blocks.append(msg),
        )

        await cs_zmq.send_to_agent(
            "agentserver",
            AgentMessage(
                from_agent="controlserver",
                to_agent="agentserver",
                message_type=MessageType.EMERGENCY_BLOCK,
                payload={
                    "block_id": "blk-bidir",
                    "severity": "admin_initiated",
                    "message": "Admin review required",
                    "affected_sessions": ["sess-bidir"],
                },
            ),
        )
        await asyncio.sleep(0.3)

        assert len(server_blocks) == 1

        # Step 3: AgentServer confirms block back to ControlServer
        confirm_msg = AgentMessage(
            from_agent="agentserver",
            to_agent="controlserver",
            message_type=MessageType.BLOCK_CONFIRMATION,
            payload={
                "block_id": "blk-bidir",
                "confirmed_sessions": ["sess-bidir"],
            },
        )
        await server_client.send_message(confirm_msg)
        await asyncio.sleep(0.3)

        confirmations = [
            m for m in cs_received
            if m.message_type == MessageType.BLOCK_CONFIRMATION
        ]
        assert len(confirmations) == 1
        assert confirmations[0].payload["block_id"] == "blk-bidir"
