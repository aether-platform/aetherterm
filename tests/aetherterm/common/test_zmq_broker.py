"""
ZMQブローカーのテスト

ブローカー登録、ルーティング、Heartbeat死活監視テスト

NOTE: The ZMQ module was removed during architecture cleanup.
These tests are skipped until the module is replaced.
"""

import asyncio
import time

import pytest
import zmq
import zmq.asyncio

from aetherterm.common.agent_protocol import AgentMessage, MessageType

pytest.importorskip("aetherterm.common.zmq", reason="ZMQ module removed during architecture cleanup")
from aetherterm.common.zmq.zmq_broker import AgentRegistration, ZMQBroker
from aetherterm.common.zmq.zmq_config import ZMQConfig
from aetherterm.common.zmq.zmq_serializer import ZMQSerializer


def _get_free_ports(count: int = 3) -> list:
    """テスト用の空きポートを取得"""
    import socket

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
    """テスト用ZMQ設定を作成"""
    return ZMQConfig(
        enabled=True,
        broker_router_endpoint=f"tcp://127.0.0.1:{ports[0]}",
        broker_pub_endpoint=f"tcp://127.0.0.1:{ports[1]}",
        broker_push_endpoint=f"tcp://127.0.0.1:{ports[2]}",
        heartbeat_interval=1,
        heartbeat_timeout=3,
    )


@pytest.fixture
def zmq_config():
    """テスト用ZMQ設定"""
    ports = _get_free_ports(3)
    return _make_config(ports)


@pytest.fixture
async def broker(zmq_config):
    """テスト用ブローカーインスタンス"""
    b = ZMQBroker(zmq_config)
    await b.start()
    yield b
    await b.stop()


class TestZMQBrokerLifecycle:
    """ブローカーライフサイクルテスト"""

    @pytest.mark.asyncio
    async def test_start_stop(self, zmq_config):
        """ブローカーの起動・停止が正常に動作すること"""
        broker = ZMQBroker(zmq_config)
        assert not broker.is_running

        await broker.start()
        assert broker.is_running
        assert broker.agent_count == 0

        await broker.stop()
        assert not broker.is_running

    @pytest.mark.asyncio
    async def test_double_start(self, zmq_config):
        """二重起動しても問題ないこと"""
        broker = ZMQBroker(zmq_config)
        await broker.start()
        await broker.start()  # 2回目は無視される
        assert broker.is_running
        await broker.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start(self, zmq_config):
        """起動前のstopがエラーにならないこと"""
        broker = ZMQBroker(zmq_config)
        await broker.stop()  # 起動前でもOK


class TestAgentRegistration:
    """Agent登録テスト"""

    @pytest.mark.asyncio
    async def test_register_agent(self, broker, zmq_config):
        """DEALERソケットからAgent登録が動作すること"""
        ctx = zmq.asyncio.Context()
        dealer = ctx.socket(zmq.DEALER)
        dealer.identity = b"test_agent_001"
        dealer.connect(zmq_config.broker_router_endpoint)

        await asyncio.sleep(0.1)  # 接続待ち

        # 登録メッセージを送信
        msg = AgentMessage(
            from_agent="test_agent_001",
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={
                "agent_id": "test_agent_001",
                "capabilities": ["pty_middleware", "command_intercept"],
            },
        )
        payload = ZMQSerializer.serialize(msg)
        await dealer.send_multipart([b"", payload])

        # ACKを受信
        frames = await asyncio.wait_for(dealer.recv_multipart(), timeout=2.0)
        assert len(frames) >= 2
        ack = ZMQSerializer.deserialize(frames[-1])
        assert ack.message_type == MessageType.AGENT_REGISTER
        assert ack.payload["status"] == "registered"

        # ブローカーのレジストリを確認
        assert broker.agent_count == 1
        reg = broker.get_agent("test_agent_001")
        assert reg is not None
        assert reg.capabilities == ["pty_middleware", "command_intercept"]

        dealer.close(linger=0)
        ctx.term()

    @pytest.mark.asyncio
    async def test_find_agents_by_capability(self, broker, zmq_config):
        """capability検索が動作すること"""
        ctx = zmq.asyncio.Context()

        # 2つのAgentを登録
        for i, caps in enumerate([["cap_a", "cap_b"], ["cap_b", "cap_c"]]):
            dealer = ctx.socket(zmq.DEALER)
            dealer.identity = f"agent_{i}".encode()
            dealer.connect(zmq_config.broker_router_endpoint)
            await asyncio.sleep(0.05)

            msg = AgentMessage(
                from_agent=f"agent_{i}",
                to_agent="broker",
                message_type=MessageType.AGENT_REGISTER,
                payload={"agent_id": f"agent_{i}", "capabilities": caps},
            )
            await dealer.send_multipart([b"", ZMQSerializer.serialize(msg)])
            await asyncio.wait_for(dealer.recv_multipart(), timeout=2.0)
            dealer.close(linger=0)

        # cap_bで検索 → 2つ見つかる
        results = broker.find_agents_by_capability("cap_b")
        assert len(results) == 2

        # cap_aで検索 → 1つ見つかる
        results = broker.find_agents_by_capability("cap_a")
        assert len(results) == 1

        # cap_xで検索 → 見つからない
        results = broker.find_agents_by_capability("cap_x")
        assert len(results) == 0

        ctx.term()


class TestMessageRouting:
    """メッセージルーティングテスト"""

    @pytest.mark.asyncio
    async def test_route_message_between_agents(self, broker, zmq_config):
        """Agent間メッセージルーティングが動作すること"""
        ctx = zmq.asyncio.Context()

        # Agent Aを登録
        dealer_a = ctx.socket(zmq.DEALER)
        dealer_a.identity = b"agent_a"
        dealer_a.connect(zmq_config.broker_router_endpoint)
        await asyncio.sleep(0.05)

        reg_a = AgentMessage(
            from_agent="agent_a",
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "agent_a", "capabilities": []},
        )
        await dealer_a.send_multipart([b"", ZMQSerializer.serialize(reg_a)])
        await asyncio.wait_for(dealer_a.recv_multipart(), timeout=2.0)

        # Agent Bを登録
        dealer_b = ctx.socket(zmq.DEALER)
        dealer_b.identity = b"agent_b"
        dealer_b.connect(zmq_config.broker_router_endpoint)
        await asyncio.sleep(0.05)

        reg_b = AgentMessage(
            from_agent="agent_b",
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "agent_b", "capabilities": []},
        )
        await dealer_b.send_multipart([b"", ZMQSerializer.serialize(reg_b)])
        await asyncio.wait_for(dealer_b.recv_multipart(), timeout=2.0)

        # Agent A → Agent B にメッセージ送信
        msg = AgentMessage(
            from_agent="agent_a",
            to_agent="agent_b",
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls -la"},
        )
        await dealer_a.send_multipart([b"", ZMQSerializer.serialize(msg)])

        # Agent Bで受信
        frames = await asyncio.wait_for(dealer_b.recv_multipart(), timeout=2.0)
        received = ZMQSerializer.deserialize(frames[-1])
        assert received.from_agent == "agent_a"
        assert received.message_type == MessageType.COMMAND_EXECUTE
        assert received.payload["command"] == "ls -la"

        dealer_a.close(linger=0)
        dealer_b.close(linger=0)
        ctx.term()


class TestPubSub:
    """PUB/SUBテスト"""

    @pytest.mark.asyncio
    async def test_publish_event(self, broker, zmq_config):
        """ブローカー経由のPUB/SUBが動作すること"""
        ctx = zmq.asyncio.Context()

        # SUBソケットを接続
        sub = ctx.socket(zmq.SUB)
        sub.connect(zmq_config.broker_pub_endpoint)
        sub.subscribe(b"terminal.output")
        await asyncio.sleep(0.2)  # SUB接続の安定化待ち

        # ブローカーからpublish
        msg = AgentMessage(
            from_agent="system",
            to_agent="",
            message_type=MessageType.TERMINAL_OUTPUT,
            payload={"data": "hello world"},
        )
        await broker.publish("terminal.output.session_123", msg)

        # SUBで受信
        frames = await asyncio.wait_for(sub.recv_multipart(), timeout=2.0)
        topic, received = ZMQSerializer.from_sub_frames(frames)
        assert topic == "terminal.output.session_123"
        assert received.payload["data"] == "hello world"

        sub.close(linger=0)
        ctx.term()


class TestHeartbeat:
    """Heartbeat死活監視テスト"""

    @pytest.mark.asyncio
    async def test_heartbeat_keeps_agent_active(self, broker, zmq_config):
        """Heartbeatを送るAgentがactiveのまま維持されること"""
        ctx = zmq.asyncio.Context()

        dealer = ctx.socket(zmq.DEALER)
        dealer.identity = b"hb_agent"
        dealer.connect(zmq_config.broker_router_endpoint)
        await asyncio.sleep(0.05)

        # 登録
        reg_msg = AgentMessage(
            from_agent="hb_agent",
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "hb_agent", "capabilities": []},
        )
        await dealer.send_multipart([b"", ZMQSerializer.serialize(reg_msg)])
        await asyncio.wait_for(dealer.recv_multipart(), timeout=2.0)

        # Heartbeat送信
        hb_msg = AgentMessage(
            from_agent="hb_agent",
            to_agent="broker",
            message_type=MessageType.AGENT_HEARTBEAT,
            payload={"agent_id": "hb_agent"},
        )
        await dealer.send_multipart([b"", ZMQSerializer.serialize(hb_msg)])
        await asyncio.sleep(0.5)

        # Agentがまだ登録されていること
        reg = broker.get_agent("hb_agent")
        assert reg is not None
        assert reg.status == "active"

        dealer.close(linger=0)
        ctx.term()

    @pytest.mark.asyncio
    async def test_agent_removed_after_heartbeat_timeout(self):
        """Heartbeatタイムアウトでagentが削除されること"""
        ports = _get_free_ports(3)
        config = ZMQConfig(
            enabled=True,
            broker_router_endpoint=f"tcp://127.0.0.1:{ports[0]}",
            broker_pub_endpoint=f"tcp://127.0.0.1:{ports[1]}",
            broker_push_endpoint=f"tcp://127.0.0.1:{ports[2]}",
            heartbeat_interval=1,
            heartbeat_timeout=2,  # 2秒でstale
        )
        broker = ZMQBroker(config)
        await broker.start()

        ctx = zmq.asyncio.Context()
        dealer = ctx.socket(zmq.DEALER)
        dealer.identity = b"timeout_agent"
        dealer.connect(config.broker_router_endpoint)
        await asyncio.sleep(0.05)

        # 登録
        msg = AgentMessage(
            from_agent="timeout_agent",
            to_agent="broker",
            message_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "timeout_agent", "capabilities": []},
        )
        await dealer.send_multipart([b"", ZMQSerializer.serialize(msg)])
        await asyncio.wait_for(dealer.recv_multipart(), timeout=2.0)

        assert broker.agent_count == 1

        # Heartbeatを送らずにタイムアウトを待つ
        # 2秒でstale, 次のinterval(1秒)でdead → 約3秒後に削除
        await asyncio.sleep(4.0)

        assert broker.agent_count == 0

        dealer.close(linger=0)
        ctx.term()
        await broker.stop()


class TestAgentRegistrationDataclass:
    """AgentRegistrationデータクラステスト"""

    def test_default_values(self):
        """デフォルト値が正しく設定されること"""
        reg = AgentRegistration(agent_id="test", identity=b"test_identity")
        assert reg.status == "active"
        assert reg.capabilities == []
        assert reg.last_heartbeat > 0
        assert reg.registered_at > 0
