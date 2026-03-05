#!/usr/bin/env python3
"""PoC: リモートコントローラ

ZMQ経由でHub(run_hub.py)のPTYを制御する。
別ターミナルで run_hub.py を起動してから実行。

使い方:
  python run_controller.py

コマンド:
  <text>          PTYにテキスト入力 (Enterで送信、自動改行付加)
  !block          Hub側で入力ブロック
  !unblock        Hub側で入力アンブロック
  !resize <r> <c> ターミナルサイズ変更
  !mode <mode>    入力モード変更 (normal/blocked/remote)
  !ping           生存確認
  !raw <data>     生データ送信 (改行なし)
  !ctrl-c         Ctrl+C送信
  !ctrl-d         Ctrl+D送信
  !quit           終了
"""

import argparse
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from zmq_remote import ZMQRemoteClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("controller")


class RemoteController:
    """インタラクティブリモートコントローラ"""

    def __init__(self, server_addr: str, control_port: int, output_port: int):
        self._client = ZMQRemoteClient(
            server_addr=server_addr,
            control_port=control_port,
            output_port=output_port,
        )
        self._running = False

    async def start(self) -> None:
        """接続して制御ループ開始"""
        # コールバック
        self._client.set_on_output(self._on_output)
        self._client.set_on_exit(self._on_exit)
        self._client.set_on_event(self._on_event)

        await self._client.connect()
        self._running = True

        # ping確認
        ok = await self._client.ping()
        if ok:
            print("\033[32m[connected] Shell server is alive\033[0m")
        else:
            print("\033[31m[error] Shell server not responding\033[0m")
            return

        # リモートモードに切り替え
        reply = await self._client.set_mode("remote")
        if reply:
            print("\033[33m[mode] Switched to REMOTE mode\033[0m")

        print("---")
        print("Commands: type text + Enter, !block, !unblock, !mode <m>,")
        print("  !resize <r> <c>, !ctrl-c, !ctrl-d, !raw <data>, !ping, !quit")
        print("---")

        # 入力ループ
        await self._input_loop()

    async def stop(self) -> None:
        """切断"""
        self._running = False
        # NORMALモードに戻す
        try:
            await self._client.set_mode("normal")
        except Exception:
            pass
        await self._client.disconnect()

    def _on_output(self, data: bytes) -> None:
        """PTY出力を表示"""
        try:
            text = data.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

    def _on_exit(self, code: int) -> None:
        """PTY終了"""
        print(f"\n\033[31m[exit] Shell exited with code {code}\033[0m")
        self._running = False

    def _on_event(self, event: dict) -> None:
        """Hub状態変更イベント"""
        etype = event.get("type", "unknown")
        if etype == "blocked":
            print("\n\033[1;31m[event] Input BLOCKED on Hub\033[0m")
        elif etype == "unblocked":
            print("\n\033[1;32m[event] Input UNBLOCKED on Hub\033[0m")
        else:
            print(f"\n\033[33m[event] {event}\033[0m")

    async def _input_loop(self) -> None:
        """ユーザー入力ループ"""
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                # stdinから非同期で1行読み取り
                line = await loop.run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break

                line = line.rstrip("\n")
                if not line:
                    # 空行→Enter送信
                    await self._client.send_input(b"\n")
                    continue

                await self._process_command(line)

            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                logger.error(f"Input error: {e}")

    async def _process_command(self, line: str) -> None:
        """コマンド処理"""
        if line == "!quit":
            await self.stop()
            return

        if line == "!ping":
            ok = await self._client.ping()
            status = "\033[32malive\033[0m" if ok else "\033[31mdead\033[0m"
            print(f"[ping] {status}")
            return

        if line == "!block":
            reply = await self._client.block()
            if reply and reply[0] == b"blocked":
                print("\033[1;31m[block] Input blocked on Hub\033[0m")
            return

        if line == "!unblock":
            reply = await self._client.unblock()
            if reply and reply[0] == b"unblocked":
                print("\033[1;32m[unblock] Input unblocked on Hub\033[0m")
            return

        if line == "!ctrl-c":
            await self._client.send_input(b"\x03")
            return

        if line == "!ctrl-d":
            await self._client.send_input(b"\x04")
            return

        if line.startswith("!raw "):
            data = line[5:].encode("utf-8")
            await self._client.send_input(data)
            return

        if line.startswith("!mode "):
            mode = line[6:].strip()
            reply = await self._client.set_mode(mode)
            if reply:
                print(f"\033[33m[mode] Response: {[f.decode() for f in reply]}\033[0m")
            return

        if line.startswith("!resize "):
            parts = line[8:].strip().split()
            if len(parts) == 2:
                rows, cols = int(parts[0]), int(parts[1])
                await self._client.send_resize(rows, cols)
                print(f"[resize] {rows}x{cols}")
            else:
                print("[error] Usage: !resize <rows> <cols>")
            return

        # 通常テキスト→PTYに送信 (改行付加)
        await self._client.send_input((line + "\n").encode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remote Controller")
    parser.add_argument(
        "--server", "-s",
        default="tcp://localhost",
        help="サーバアドレス (デフォルト: tcp://localhost)",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=15555,
        help="ZMQ制御ポート",
    )
    parser.add_argument(
        "--output-port",
        type=int,
        default=15556,
        help="ZMQ出力ポート",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    controller = RemoteController(
        server_addr=args.server,
        control_port=args.control_port,
        output_port=args.output_port,
    )

    try:
        await controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        await controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
