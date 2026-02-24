"""
ZMQシリアライザ

AgentMessage ↔ ZMQマルチパートフレーム変換を行います。
シリアライズにはmsgpackを使用（JSONより高速・コンパクト）。

フレーム構造:
  ROUTER/DEALER: [identity, b'', msgpack(AgentMessage.to_dict())]
  PUB/SUB:       [topic_bytes, msgpack(AgentMessage.to_dict())]
"""

import logging
from typing import List, Optional, Tuple

import msgpack

from ..agent_protocol import AgentMessage

logger = logging.getLogger(__name__)


class ZMQSerializer:
    """AgentMessageとZMQフレーム間のシリアライズ/デシリアライズ"""

    @staticmethod
    def serialize(message: AgentMessage) -> bytes:
        """AgentMessageをmsgpackバイト列にシリアライズ"""
        return msgpack.packb(message.to_dict(), use_bin_type=True)

    @staticmethod
    def deserialize(data: bytes) -> AgentMessage:
        """msgpackバイト列からAgentMessageをデシリアライズ"""
        unpacked = msgpack.unpackb(data, raw=False)
        return AgentMessage.from_dict(unpacked)

    @staticmethod
    def to_router_frames(
        identity: bytes, message: AgentMessage
    ) -> List[bytes]:
        """
        ROUTER/DEALERフレームに変換

        Returns:
            [identity, b'', msgpack_payload]
        """
        payload = ZMQSerializer.serialize(message)
        return [identity, b"", payload]

    @staticmethod
    def from_router_frames(
        frames: List[bytes],
    ) -> Tuple[bytes, AgentMessage]:
        """
        ROUTER/DEALERフレームからデシリアライズ

        Args:
            frames: [identity, b'', msgpack_payload]

        Returns:
            (identity, AgentMessage)
        """
        if len(frames) < 3:
            raise ValueError(
                f"Invalid ROUTER frame: expected >=3 parts, got {len(frames)}"
            )
        identity = frames[0]
        # frames[1] is delimiter (b'')
        message = ZMQSerializer.deserialize(frames[2])
        return identity, message

    @staticmethod
    def to_pub_frames(topic: str, message: AgentMessage) -> List[bytes]:
        """
        PUB/SUBフレームに変換

        Returns:
            [topic_bytes, msgpack_payload]
        """
        payload = ZMQSerializer.serialize(message)
        return [topic.encode("utf-8"), payload]

    @staticmethod
    def from_sub_frames(
        frames: List[bytes],
    ) -> Tuple[str, AgentMessage]:
        """
        PUB/SUBフレームからデシリアライズ

        Args:
            frames: [topic_bytes, msgpack_payload]

        Returns:
            (topic, AgentMessage)
        """
        if len(frames) < 2:
            raise ValueError(
                f"Invalid PUB frame: expected >=2 parts, got {len(frames)}"
            )
        topic = frames[0].decode("utf-8")
        message = ZMQSerializer.deserialize(frames[1])
        return topic, message
