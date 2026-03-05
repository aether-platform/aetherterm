#!/usr/bin/env python3
"""PoC: Hub (AgentServer相当)

PTY管理 + ZMQサーバを持つ。
Shellはfork/execされたpure childプロセス(bash等)。

アーキテクチャ:
  run_controller.py ◄── ZMQ ──► run_hub.py ──► [bash] (pure child)

使い方:
  python run_hub.py
  python run_hub.py --shell zsh
  python run_hub.py --command "python3 -i"
"""

import argparse
import asyncio
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from async_pty import AsyncPTY, InputMode
from zmq_remote import ZMQRemoteServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("hub.log"), logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("hub")

# シェルプリセット
SHELL_PRESETS = {
    "bash": ["/bin/bash", "--norc"],
    "zsh": ["/bin/zsh"],
    "sh": ["/bin/sh"],
    "python": ["python3", "-i"],
    "node": ["node"],
}


class Hub:
    """Hub: PTY管理 + ZMQ通信

    - AsyncPTY: fork/execでshellを起動、PTY I/O管理
    - ZMQRemoteServer: リモートコントローラからの制御受付、出力配信
    - Shell(child process)は純粋なbash等、ネットワーク機能なし
    """

    def __init__(
        self,
        command: list[str],
        initial_mode: InputMode = InputMode.NORMAL,
        control_port: int = 15555,
        output_port: int = 15556,
    ):
        self._pty = AsyncPTY(command=command)
        self._zmq = ZMQRemoteServer(
            control_port=control_port,
            output_port=output_port,
        )
        self._initial_mode = initial_mode
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        # ZMQ起動
        self._zmq.set_on_input(self._on_remote_input)
        self._zmq.set_on_resize(self._on_remote_resize)
        self._zmq.set_on_mode_change(self._on_remote_mode_change)
        self._zmq.set_on_block(self._on_remote_block)
        self._zmq.set_on_unblock(self._on_remote_unblock)
        await self._zmq.start()

        # PTY起動 (fork/exec shell)
        self._pty.set_on_output(self._on_pty_output)
        self._pty.set_on_exit(self._on_pty_exit)
        await self._pty.start()
        self._pty.input_mode = self._initial_mode

        logger.info(
            f"Hub started: pid={self._pty.child_pid}, "
            f"mode={self._initial_mode.name}"
        )

        # シグナル
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.stop()))

        await self._shutdown.wait()

    async def stop(self) -> None:
        if self._shutdown.is_set():
            return
        await self._pty.stop()
        await self._zmq.stop()
        self._shutdown.set()
        logger.info("Hub stopped")

    # -- PTY callbacks --

    def _on_pty_output(self, data: bytes) -> None:
        """PTY出力 → stdout表示 + ZMQ配信"""
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        asyncio.ensure_future(self._zmq.publish_output(data))

    def _on_pty_exit(self, code: int) -> None:
        """Shell子プロセス終了"""
        logger.info(f"Shell exited: code={code}")
        asyncio.ensure_future(self._zmq.publish_exit(code))
        asyncio.ensure_future(self.stop())

    # -- ZMQ remote callbacks --

    async def _on_remote_input(self, data: bytes) -> None:
        """リモート入力 → PTYに注入"""
        await self._pty.write_input(data)

    async def _on_remote_resize(self, rows: int, cols: int) -> None:
        """リモートリサイズ"""
        await self._pty.resize(rows, cols)

    async def _on_remote_mode_change(self, mode: InputMode) -> None:
        """リモートモード切替"""
        self._pty.input_mode = mode

    async def _on_remote_block(self) -> None:
        """リモートから入力ブロック指示"""
        self._pty.input_mode = InputMode.BLOCKED
        logger.info("Input BLOCKED by remote")

    async def _on_remote_unblock(self) -> None:
        """リモートから入力アンブロック指示"""
        self._pty.input_mode = InputMode.NORMAL
        logger.info("Input UNBLOCKED by remote")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PoC Hub")
    parser.add_argument(
        "--shell", "-s",
        choices=list(SHELL_PRESETS.keys()),
        default=None,
        help=f"シェルプリセット ({', '.join(SHELL_PRESETS.keys())})",
    )
    parser.add_argument(
        "--command", "-c",
        type=str,
        default=None,
        help="任意コマンド (--shellより優先)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["normal", "blocked", "remote"],
        default="normal",
        help="初期入力モード",
    )
    parser.add_argument("--control-port", type=int, default=15555)
    parser.add_argument("--output-port", type=int, default=15556)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # コマンド決定: --command > --shell > デフォルトbash
    if args.command:
        command = args.command.split()
    elif args.shell:
        command = SHELL_PRESETS[args.shell]
    else:
        command = SHELL_PRESETS["bash"]

    mode_map = {
        "normal": InputMode.NORMAL,
        "blocked": InputMode.BLOCKED,
        "remote": InputMode.REMOTE,
    }

    hub = Hub(
        command=command,
        initial_mode=mode_map[args.mode],
        control_port=args.control_port,
        output_port=args.output_port,
    )

    try:
        await hub.start()
    except KeyboardInterrupt:
        pass
    finally:
        await hub.stop()


if __name__ == "__main__":
    asyncio.run(main())
