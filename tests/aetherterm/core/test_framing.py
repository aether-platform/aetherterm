"""Tests for core/ws/framing — binary frame encode/decode."""

from aetherterm.core.ws.framing import decode_binary_frame, encode_binary_frame


class TestEncodeDecode:
    def test_roundtrip(self):
        frame = encode_binary_frame("pane_abc", b"hello world")
        pane_id, data = decode_binary_frame(frame)
        assert pane_id == "pane_abc"
        assert data == b"hello world"

    def test_empty_data(self):
        frame = encode_binary_frame("p1", b"")
        pane_id, data = decode_binary_frame(frame)
        assert pane_id == "p1"
        assert data == b""

    def test_empty_frame(self):
        pane_id, data = decode_binary_frame(b"")
        assert pane_id == ""
        assert data == b""

    def test_binary_data(self):
        payload = bytes(range(256))
        frame = encode_binary_frame("bin", payload)
        pane_id, data = decode_binary_frame(frame)
        assert pane_id == "bin"
        assert data == payload

    def test_long_pane_id(self):
        long_id = "a" * 200  # max 255 bytes (1 byte length field)
        frame = encode_binary_frame(long_id, b"x")
        pane_id, data = decode_binary_frame(frame)
        assert pane_id == long_id
        assert data == b"x"

    def test_unicode_pane_id(self):
        frame = encode_binary_frame("pane_日本語", b"data")
        pane_id, data = decode_binary_frame(frame)
        assert pane_id == "pane_日本語"
        assert data == b"data"

    def test_frame_structure(self):
        """Verify wire format: [1B len][pane_id][data]."""
        frame = encode_binary_frame("ab", b"\x01\x02")
        assert frame[0] == 2  # pane_id length
        assert frame[1:3] == b"ab"
        assert frame[3:] == b"\x01\x02"
