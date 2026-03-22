"""Tests for core/pty/manager — PTYManager spawn/kill integration tests."""

import asyncio
import os

import pytest

from aetherterm.core.pty.manager import PTYManager


@pytest.fixture
async def manager():
    mgr = PTYManager()
    yield mgr
    await mgr.cleanup_all()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires Unix fork()")
class TestPTYManagerSpawn:
    @pytest.mark.asyncio
    async def test_spawn_and_get(self, manager):
        session = await manager.spawn("test1", cmd=["/bin/echo", "hello"])
        assert session.session_id == "test1"
        assert session.pid > 0
        assert session.master_fd >= 0
        assert manager.get("test1") is session

    @pytest.mark.asyncio
    async def test_spawn_duplicate_returns_existing(self, manager):
        s1 = await manager.spawn("dup", cmd=["/bin/echo", "a"])
        s2 = await manager.spawn("dup", cmd=["/bin/echo", "b"])
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_spawn_with_env(self, manager):
        session = await manager.spawn(
            "env_test",
            cmd=["/bin/bash", "-c", "echo $MY_VAR"],
            env={"MY_VAR": "test_value"},
        )
        # Read output
        q = session.subscribe()
        await asyncio.sleep(0.3)
        chunks = []
        while not q.empty():
            data = q.get_nowait()
            if data is not None:
                chunks.append(data)
        output = b"".join(chunks).decode()
        assert "test_value" in output

    @pytest.mark.asyncio
    async def test_spawn_with_cwd(self, manager):
        session = await manager.spawn(
            "cwd_test",
            cmd=["/bin/pwd"],
            cwd="/tmp",
        )
        q = session.subscribe()
        await asyncio.sleep(0.3)
        chunks = []
        while not q.empty():
            data = q.get_nowait()
            if data is not None:
                chunks.append(data)
        output = b"".join(chunks).decode().strip()
        assert output.endswith("/tmp")

    @pytest.mark.asyncio
    async def test_list_all(self, manager):
        await manager.spawn("a", cmd=["/bin/sleep", "10"])
        await manager.spawn("b", cmd=["/bin/sleep", "10"])
        assert len(manager.list_all()) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, manager):
        assert manager.get("nope") is None


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires Unix fork()")
class TestPTYManagerKill:
    @pytest.mark.asyncio
    async def test_kill(self, manager):
        session = await manager.spawn("kill_me", cmd=["/bin/sleep", "60"])
        q = session.subscribe()
        await manager.kill("kill_me")
        assert manager.get("kill_me") is None
        # Client should receive EOF
        eof = await asyncio.wait_for(q.get(), timeout=2.0)
        assert eof is None

    @pytest.mark.asyncio
    async def test_kill_nonexistent(self, manager):
        await manager.kill("no_such_session")  # should not raise

    @pytest.mark.asyncio
    async def test_cleanup_all(self, manager):
        await manager.spawn("x", cmd=["/bin/sleep", "60"])
        await manager.spawn("y", cmd=["/bin/sleep", "60"])
        await manager.cleanup_all()
        assert len(manager.list_all()) == 0


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires Unix fork()")
class TestPTYManagerReadLoop:
    @pytest.mark.asyncio
    async def test_output_reaches_clients(self, manager):
        session = await manager.spawn("reader", cmd=["/bin/echo", "ping"])
        q = session.subscribe()
        await asyncio.sleep(0.3)
        chunks = []
        while not q.empty():
            data = q.get_nowait()
            if data is not None:
                chunks.append(data)
        output = b"".join(chunks).decode()
        assert "ping" in output

    @pytest.mark.asyncio
    async def test_output_stored_in_history(self, manager):
        session = await manager.spawn("hist", cmd=["/bin/echo", "remember_me"])
        await asyncio.sleep(0.3)
        assert b"remember_me" in session.history

    @pytest.mark.asyncio
    async def test_output_callback(self, manager):
        received = []

        async def on_output(session_id, data):
            received.append((session_id, data))

        manager.on_output(on_output)
        await manager.spawn("cb_test", cmd=["/bin/echo", "callback"])
        await asyncio.sleep(0.3)
        assert any(b"callback" in data for _, data in received)

    @pytest.mark.asyncio
    async def test_process_exit_removes_session(self, manager):
        """When child exits, read loop should remove session."""
        await manager.spawn("short", cmd=["/bin/echo", "bye"])
        await asyncio.sleep(0.5)  # Wait for echo to exit + read loop cleanup
        assert manager.get("short") is None
