"""
ZMQシリアライザのテスト

AgentMessage ↔ ZMQフレーム往復テスト

NOTE: The ZMQ module was removed during architecture cleanup.
These tests are skipped until the module is replaced.
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime

from aetherterm.common.agent_protocol import AgentMessage, MessageType

pytest.importorskip("aetherterm.common.zmq", reason="ZMQ module removed during architecture cleanup")
from aetherterm.common.zmq.zmq_serializer import ZMQSerializer


class TestZMQSerializer:
    """ZMQSerializer単体テスト"""

    def _make_message(self, **kwargs) -> AgentMessage:
        """テスト用メッセージを作成"""
        defaults = {
            "from_agent": "agent_A",
            "to_agent": "agent_B",
            "message_type": MessageType.STATUS_UPDATE,
            "payload": {"key": "value", "number": 42},
        }
        defaults.update(kwargs)
        return AgentMessage(**defaults)

    def test_serialize_deserialize_roundtrip(self):
        """シリアライズ→デシリアライズで元のメッセージが復元されること"""
        original = self._make_message()
        data = ZMQSerializer.serialize(original)
        restored = ZMQSerializer.deserialize(data)

        assert str(restored.message_id) == str(original.message_id)
        assert restored.from_agent == original.from_agent
        assert restored.to_agent == original.to_agent
        assert restored.message_type == original.message_type
        assert restored.payload == original.payload

    def test_serialize_produces_bytes(self):
        """シリアライズ結果がbytes型であること"""
        msg = self._make_message()
        data = ZMQSerializer.serialize(msg)
        assert isinstance(data, bytes)

    def test_deserialize_invalid_data_raises(self):
        """不正データのデシリアライズでエラーが発生すること"""
        with pytest.raises(Exception):
            ZMQSerializer.deserialize(b"invalid data")

    def test_correlation_id_preserved(self):
        """correlation_idが往復で保持されること"""
        cid = uuid4()
        msg = self._make_message(correlation_id=cid)
        data = ZMQSerializer.serialize(msg)
        restored = ZMQSerializer.deserialize(data)
        assert str(restored.correlation_id) == str(cid)

    def test_reply_to_preserved(self):
        """reply_toが往復で保持されること"""
        reply_id = uuid4()
        msg = self._make_message(reply_to=reply_id)
        data = ZMQSerializer.serialize(msg)
        restored = ZMQSerializer.deserialize(data)
        assert str(restored.reply_to) == str(reply_id)

    def test_none_optional_fields(self):
        """correlation_id/reply_toがNoneでも正常に往復すること"""
        msg = self._make_message(correlation_id=None, reply_to=None)
        data = ZMQSerializer.serialize(msg)
        restored = ZMQSerializer.deserialize(data)
        assert restored.correlation_id is None
        assert restored.reply_to is None

    def test_all_message_types(self):
        """全MessageTypeでシリアライズ/デシリアライズが動作すること"""
        for mt in MessageType:
            msg = self._make_message(message_type=mt)
            data = ZMQSerializer.serialize(msg)
            restored = ZMQSerializer.deserialize(data)
            assert restored.message_type == mt

    def test_complex_payload(self):
        """ネストされたpayloadが正しく往復すること"""
        payload = {
            "nested": {"deep": {"value": [1, 2, 3]}},
            "list": [{"a": 1}, {"b": 2}],
            "bool": True,
            "null": None,
        }
        msg = self._make_message(payload=payload)
        data = ZMQSerializer.serialize(msg)
        restored = ZMQSerializer.deserialize(data)
        assert restored.payload == payload


class TestZMQRouterFrames:
    """ROUTER/DEALERフレーム変換テスト"""

    def _make_message(self) -> AgentMessage:
        return AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND_EXECUTE,
            payload={"command": "ls -la"},
        )

    def test_to_router_frames_structure(self):
        """ROUTERフレームが[identity, b'', payload]の3パートであること"""
        identity = b"agent_001"
        msg = self._make_message()
        frames = ZMQSerializer.to_router_frames(identity, msg)

        assert len(frames) == 3
        assert frames[0] == identity
        assert frames[1] == b""
        assert isinstance(frames[2], bytes)

    def test_router_frames_roundtrip(self):
        """ROUTERフレーム変換の往復テスト"""
        identity = b"agent_001"
        original = self._make_message()
        frames = ZMQSerializer.to_router_frames(identity, original)
        restored_identity, restored_msg = ZMQSerializer.from_router_frames(frames)

        assert restored_identity == identity
        assert str(restored_msg.message_id) == str(original.message_id)
        assert restored_msg.from_agent == original.from_agent
        assert restored_msg.payload == original.payload

    def test_from_router_frames_too_few_parts(self):
        """フレーム数不足でValueErrorが発生すること"""
        with pytest.raises(ValueError, match="expected >=3"):
            ZMQSerializer.from_router_frames([b"identity", b""])


class TestZMQPubFrames:
    """PUB/SUBフレーム変換テスト"""

    def _make_message(self) -> AgentMessage:
        return AgentMessage(
            from_agent="publisher",
            to_agent="",
            message_type=MessageType.STATUS_UPDATE,
            payload={"status": "running"},
        )

    def test_to_pub_frames_structure(self):
        """PUBフレームが[topic_bytes, payload]の2パートであること"""
        topic = "terminal.output.session_123"
        msg = self._make_message()
        frames = ZMQSerializer.to_pub_frames(topic, msg)

        assert len(frames) == 2
        assert frames[0] == topic.encode("utf-8")
        assert isinstance(frames[1], bytes)

    def test_pub_frames_roundtrip(self):
        """PUBフレーム変換の往復テスト"""
        topic = "agent.status.agent_001"
        original = self._make_message()
        frames = ZMQSerializer.to_pub_frames(topic, original)
        restored_topic, restored_msg = ZMQSerializer.from_sub_frames(frames)

        assert restored_topic == topic
        assert str(restored_msg.message_id) == str(original.message_id)
        assert restored_msg.payload == original.payload

    def test_from_sub_frames_too_few_parts(self):
        """フレーム数不足でValueErrorが発生すること"""
        with pytest.raises(ValueError, match="expected >=2"):
            ZMQSerializer.from_sub_frames([b"topic_only"])

    def test_unicode_topic(self):
        """Unicode文字を含むトピックの往復テスト"""
        topic = "system.broadcast"
        msg = self._make_message()
        frames = ZMQSerializer.to_pub_frames(topic, msg)
        restored_topic, _ = ZMQSerializer.from_sub_frames(frames)
        assert restored_topic == topic
