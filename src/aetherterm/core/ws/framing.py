"""Binary frame encoding for multiplexed PTY I/O over WebSocket.

Frame format: [1 byte: pane_id_len][N bytes: pane_id][M bytes: pty_data]

Used by both agentserver (tmux WebSocket) and agiterm (workspace WebSocket)
to multiplex multiple pane outputs over a single connection.
"""

from __future__ import annotations

import struct


def encode_binary_frame(pane_id: str, data: bytes) -> bytes:
    """Encode a binary frame: [1 byte len][pane_id bytes][data bytes]."""
    pane_bytes = pane_id.encode("utf-8")
    return struct.pack("B", len(pane_bytes)) + pane_bytes + data


def decode_binary_frame(frame: bytes) -> tuple[str, bytes]:
    """Decode a binary frame back to (pane_id, data).

    Returns ("", b"") for empty frames.
    """
    if not frame:
        return ("", b"")
    pane_id_len = frame[0]
    pane_id = frame[1 : 1 + pane_id_len].decode("utf-8")
    data = frame[1 + pane_id_len :]
    return (pane_id, data)
