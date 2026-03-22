"""WebSocket protocol utilities shared across services."""

from .framing import decode_binary_frame, encode_binary_frame

__all__ = ["decode_binary_frame", "encode_binary_frame"]
