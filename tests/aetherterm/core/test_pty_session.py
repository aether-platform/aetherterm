"""Tests for core/pty/session — PTYSession unit tests."""

import asyncio

from aetherterm.core.pty.session import MAX_HISTORY, TRIM_HISTORY, PTYSession


class TestPTYSessionBasic:
    def test_init(self):
        s = PTYSession("s1", master_fd=10, pid=1234)
        assert s.session_id == "s1"
        assert s.id == "s1"  # backward compat alias
        assert s.master_fd == 10
        assert s.pid == 1234
        assert s.cols == 80
        assert s.rows == 24
        assert s.history == bytearray()
        assert len(s.clients) == 0

    def test_init_custom_size(self):
        s = PTYSession("s2", master_fd=10, pid=1, cols=120, rows=40)
        assert s.cols == 120
        assert s.rows == 40


class TestPTYSessionHistory:
    def test_append_history(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        s.append_history(b"hello")
        assert s.history == bytearray(b"hello")
        s.append_history(b" world")
        assert s.history == bytearray(b"hello world")

    def test_trim_history(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        # Fill beyond MAX_HISTORY
        big = b"x" * (MAX_HISTORY + 100)
        s.append_history(big)
        assert len(s.history) == TRIM_HISTORY


class TestPTYSessionBroadcast:
    def test_broadcast(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        q1 = s.subscribe()
        q2 = s.subscribe()
        assert len(s.clients) == 2

        s.broadcast(b"data")
        assert q1.get_nowait() == b"data"
        assert q2.get_nowait() == b"data"

    def test_unsubscribe(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        q = s.subscribe()
        assert len(s.clients) == 1
        s.unsubscribe(q)
        assert len(s.clients) == 0

    def test_unsubscribe_idempotent(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        q = asyncio.Queue()
        s.unsubscribe(q)  # not subscribed — no error
        assert len(s.clients) == 0

    def test_signal_clients_eof(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        q = s.subscribe()
        s.signal_clients_eof()
        assert q.get_nowait() is None

    def test_broadcast_skips_full_queue(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        q = asyncio.Queue(maxsize=1)
        s.clients.add(q)
        q.put_nowait(b"first")
        # Queue is full — broadcast should not raise
        s.broadcast(b"second")
        assert q.get_nowait() == b"first"


class TestPTYSessionFd:
    def test_close_fd(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        s.close_fd()  # already -1, should not error
        assert s.master_fd == -1

    def test_is_alive_no_pid(self):
        s = PTYSession("s1", master_fd=-1, pid=0)
        assert s.is_alive is False

    def test_is_alive_negative_pid(self):
        s = PTYSession("s1", master_fd=-1, pid=-1)
        assert s.is_alive is False
