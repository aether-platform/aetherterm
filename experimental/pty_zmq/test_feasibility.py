#!/usr/bin/env python3
"""フィージビリティスタディ: 自動テスト

1プロセス内でPTY + ZMQサーバ + ZMQクライアントを起動し、
各機能の動作を自動検証する。

テスト項目:
  1. PTYオープン (bash)
  2. PTYオープン (カスタムコマンド)
  3. ユーザー入力ブロック (BLOCKED mode)
  4. ZMQ経由リモート入力 (REMOTE mode)
  5. ZMQ経由モード切替
  6. ZMQ経由リサイズ
  7. PTY出力のZMQ配信
  8. ZMQ経由 block/unblock (Hub側入力ブロック)
"""

import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from async_pty import AsyncPTY, InputMode
from zmq_remote import ZMQRemoteClient, ZMQRemoteServer

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test")


class OutputCollector:
    """PTY出力を収集"""

    def __init__(self):
        self.chunks: list[bytes] = []
        self.total_bytes = 0

    def on_output(self, data: bytes) -> None:
        self.chunks.append(data)
        self.total_bytes += len(data)

    @property
    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8", errors="replace")

    def clear(self) -> None:
        self.chunks.clear()
        self.total_bytes = 0


def result(name: str, passed: bool, detail: str = "") -> None:
    mark = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
    suffix = f" ({detail})" if detail else ""
    print(f"  [{mark}] {name}{suffix}")


async def test_pty_open_bash() -> bool:
    """Test 1: PTYオープン (bash)"""
    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    collector = OutputCollector()
    pty.set_on_output(collector.on_output)
    pty._input_mode = InputMode.BLOCKED

    await pty.start()
    assert pty.is_running
    assert pty.child_pid is not None

    await pty.write_input(b"echo HELLO_PTY\n")
    await asyncio.sleep(0.5)
    await pty.stop()

    return "HELLO_PTY" in collector.text


async def test_pty_open_custom_command() -> bool:
    """Test 2: PTYオープン (カスタムコマンド)"""
    pty = AsyncPTY(command=["python3", "-c", "print('CUSTOM_CMD_OK')"])
    collector = OutputCollector()
    pty.set_on_output(collector.on_output)
    pty._input_mode = InputMode.BLOCKED

    await pty.start()
    await asyncio.sleep(1.0)
    output = collector.text
    await pty.stop()

    return "CUSTOM_CMD_OK" in output


async def test_input_blocked_mode() -> bool:
    """Test 3: BLOCKEDモードでstdinブロック、write_input()は通る"""
    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    collector = OutputCollector()
    pty.set_on_output(collector.on_output)
    pty._input_mode = InputMode.BLOCKED

    await pty.start()
    await asyncio.sleep(0.3)

    collector.clear()
    await pty.write_input(b"echo INJECTED_OK\n")
    await asyncio.sleep(0.5)
    await pty.stop()

    return "INJECTED_OK" in collector.text


async def test_zmq_remote_input() -> bool:
    """Test 4: ZMQ経由リモート入力"""
    ctrl_port = 16555
    out_port = 16556

    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    collector = OutputCollector()
    pty.set_on_output(collector.on_output)
    pty._input_mode = InputMode.REMOTE

    zmq_server = ZMQRemoteServer(control_port=ctrl_port, output_port=out_port)
    zmq_server.set_on_input(pty.write_input)

    zmq_client = ZMQRemoteClient(control_port=ctrl_port, output_port=out_port)

    await pty.start()
    await zmq_server.start()
    await zmq_client.connect()
    await asyncio.sleep(0.5)

    ok = await zmq_client.ping()
    if not ok:
        await pty.stop()
        await zmq_server.stop()
        await zmq_client.disconnect()
        return False

    collector.clear()
    await zmq_client.send_input(b"echo ZMQ_REMOTE_OK\n")
    await asyncio.sleep(1.0)

    has_local = "ZMQ_REMOTE_OK" in collector.text

    await pty.stop()
    await zmq_server.stop()
    await zmq_client.disconnect()

    return has_local


async def test_zmq_mode_switch() -> bool:
    """Test 5: ZMQ経由モード切替"""
    ctrl_port = 17555
    out_port = 17556

    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    pty._input_mode = InputMode.BLOCKED

    mode_changes: list[InputMode] = []

    async def on_mode(mode: InputMode):
        pty._input_mode = mode
        mode_changes.append(mode)

    zmq_server = ZMQRemoteServer(control_port=ctrl_port, output_port=out_port)
    zmq_server.set_on_input(pty.write_input)
    zmq_server.set_on_mode_change(on_mode)

    zmq_client = ZMQRemoteClient(control_port=ctrl_port, output_port=out_port)

    await pty.start()
    await zmq_server.start()
    await zmq_client.connect()
    await asyncio.sleep(0.3)

    await zmq_client.set_mode("remote")
    await asyncio.sleep(0.2)
    await zmq_client.set_mode("normal")
    await asyncio.sleep(0.2)
    await zmq_client.set_mode("blocked")
    await asyncio.sleep(0.2)

    await pty.stop()
    await zmq_server.stop()
    await zmq_client.disconnect()

    expected = [InputMode.REMOTE, InputMode.NORMAL, InputMode.BLOCKED]
    return mode_changes == expected


async def test_zmq_resize() -> bool:
    """Test 6: ZMQ経由リサイズ"""
    ctrl_port = 18555
    out_port = 18556

    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"], rows=24, cols=80)
    pty._input_mode = InputMode.BLOCKED

    zmq_server = ZMQRemoteServer(control_port=ctrl_port, output_port=out_port)

    async def on_resize(rows, cols):
        await pty.resize(rows, cols)

    zmq_server.set_on_resize(on_resize)

    zmq_client = ZMQRemoteClient(control_port=ctrl_port, output_port=out_port)

    await pty.start()
    await zmq_server.start()
    await zmq_client.connect()
    await asyncio.sleep(0.3)

    reply = await zmq_client.send_resize(50, 120)
    await asyncio.sleep(0.3)

    resized = pty._rows == 50 and pty._cols == 120

    await pty.stop()
    await zmq_server.stop()
    await zmq_client.disconnect()

    return resized and reply is not None


async def test_output_pub_sub() -> bool:
    """Test 7: PTY出力のZMQ PUB/SUB配信"""
    ctrl_port = 19555
    out_port = 19556

    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    pty._input_mode = InputMode.BLOCKED

    zmq_server = ZMQRemoteServer(control_port=ctrl_port, output_port=out_port)
    zmq_server.set_on_input(pty.write_input)

    def on_pty_output(data: bytes):
        asyncio.ensure_future(zmq_server.publish_output(data))

    pty.set_on_output(on_pty_output)

    zmq_client = ZMQRemoteClient(control_port=ctrl_port, output_port=out_port)
    remote_output = OutputCollector()
    zmq_client.set_on_output(remote_output.on_output)

    await pty.start()
    await zmq_server.start()
    await zmq_client.connect()
    await asyncio.sleep(1.0)  # slow joiner

    await zmq_client.send_input(b"echo PUB_SUB_TEST_12345\n")
    await asyncio.sleep(1.0)

    has_output = "PUB_SUB_TEST_12345" in remote_output.text

    await pty.stop()
    await zmq_server.stop()
    await zmq_client.disconnect()

    return has_output


async def test_zmq_block_unblock() -> bool:
    """Test 8: ZMQ経由 block/unblock (Hub側入力ブロック)"""
    ctrl_port = 20555
    out_port = 20556

    pty = AsyncPTY(command=["/bin/bash", "--norc", "--noprofile"])
    collector = OutputCollector()
    pty.set_on_output(collector.on_output)
    pty._input_mode = InputMode.NORMAL  # 最初はNORMAL

    block_called = False
    unblock_called = False

    async def on_block():
        nonlocal block_called
        block_called = True
        pty._input_mode = InputMode.BLOCKED

    async def on_unblock():
        nonlocal unblock_called
        unblock_called = True
        pty._input_mode = InputMode.NORMAL

    zmq_server = ZMQRemoteServer(control_port=ctrl_port, output_port=out_port)
    zmq_server.set_on_input(pty.write_input)
    zmq_server.set_on_block(on_block)
    zmq_server.set_on_unblock(on_unblock)

    # イベント収集
    events: list[dict] = []
    zmq_client = ZMQRemoteClient(control_port=ctrl_port, output_port=out_port)
    zmq_client.set_on_event(lambda e: events.append(e))

    await pty.start()
    await zmq_server.start()
    await zmq_client.connect()
    await asyncio.sleep(0.5)

    # block
    reply = await zmq_client.block()
    await asyncio.sleep(0.3)
    is_blocked = (
        reply is not None
        and reply[0] == b"blocked"
        and block_called
        and pty._input_mode == InputMode.BLOCKED
    )

    # unblock
    reply = await zmq_client.unblock()
    await asyncio.sleep(0.3)
    is_unblocked = (
        reply is not None
        and reply[0] == b"unblocked"
        and unblock_called
        and pty._input_mode == InputMode.NORMAL
    )

    # PUBイベント確認
    await asyncio.sleep(0.5)
    event_types = [e.get("type") for e in events]
    has_events = "blocked" in event_types and "unblocked" in event_types

    await pty.stop()
    await zmq_server.stop()
    await zmq_client.disconnect()

    return is_blocked and is_unblocked and has_events


async def run_tests() -> None:
    """全テスト実行"""
    print("\n=== AgentShell Feasibility Study ===\n")

    tests = [
        ("PTY open (bash)", test_pty_open_bash),
        ("PTY open (custom command)", test_pty_open_custom_command),
        ("Input BLOCKED mode", test_input_blocked_mode),
        ("ZMQ remote input", test_zmq_remote_input),
        ("ZMQ mode switch", test_zmq_mode_switch),
        ("ZMQ resize", test_zmq_resize),
        ("ZMQ PUB/SUB output", test_output_pub_sub),
        ("ZMQ block/unblock", test_zmq_block_unblock),
    ]

    passed = 0
    failed = 0
    start = time.time()

    for name, test_fn in tests:
        try:
            ok = await test_fn()
            result(name, ok)
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            result(name, False, str(e))
            failed += 1

    elapsed = time.time() - start
    print(f"\n  Total: {passed + failed}, Passed: {passed}, "
          f"Failed: {failed}, Time: {elapsed:.1f}s\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
