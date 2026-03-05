#!/usr/bin/env python3
"""リアルタイムコマンド解析デモ

PTYモニターと連携して、実際のターミナルセッションで
リアルタイムにコマンドを解析・監視するデモです。
"""

import asyncio
import logging
import os
import pty
import select
import sys
import termios
import tty
from datetime import datetime
from typing import Dict, List, Optional

from ...agents import AgentManager
from ...pty_monitor import CommandInterceptor

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RealtimeCommandAnalysisDemo:
    """リアルタイムコマンド解析デモクラス"""

    def __init__(self):
        self.agent_manager = AgentManager()
        self.interceptor: Optional[CommandInterceptor] = None
        self.original_tty_attrs: Optional[List] = None

        # デモ用の設定
        self.show_analysis = True  # 解析結果を表示
        self.auto_block = True  # 危険なコマンドを自動ブロック

        # 統計
        self.demo_stats = {
            "start_time": None,
            "end_time": None,
            "commands_analyzed": 0,
            "dangerous_commands": 0,
            "blocked_commands": 0,
        }

    async def setup(self):
        """デモ環境をセットアップ"""
        logger.info("リアルタイムコマンド解析デモをセットアップ中...")

        # コマンドインターセプターを作成
        self.interceptor = CommandInterceptor(
            agent_manager=self.agent_manager, auto_block_dangerous=self.auto_block
        )

        # コールバックを設定
        self.interceptor.on_command_analyzed = self._on_command_analyzed
        self.interceptor.on_command_blocked = self._on_command_blocked
        self.interceptor.on_user_approval = self._on_user_approval

        # インターセプターを初期化
        await self.interceptor.initialize()

        self.demo_stats["start_time"] = datetime.now()

        logger.info("デモ環境のセットアップが完了しました")

    async def teardown(self):
        """デモ環境をクリーンアップ"""
        logger.info("デモ環境をクリーンアップ中...")

        if self.interceptor:
            await self.interceptor.shutdown()

        self.demo_stats["end_time"] = datetime.now()

        # デモ統計を表示
        self._print_demo_statistics()

        logger.info("デモ環境のクリーンアップが完了しました")

    def _on_command_analyzed(self, result: Dict[str, Any]):
        """コマンド解析完了時のコールバック"""
        self.demo_stats["commands_analyzed"] += 1

        if not self.show_analysis:
            return

        # 解析結果を表示
        command = result.get("command", "")
        safety = result.get("safety", {})
        risk_level = safety.get("risk_level", "unknown")

        # リスクレベルに応じた色付け
        color_map = {
            "safe": "\033[32m",  # 緑
            "caution": "\033[33m",  # 黄
            "dangerous": "\033[91m",  # 赤（明るい）
            "critical": "\033[31m",  # 赤（暗い）
        }
        color = color_map.get(risk_level, "\033[0m")
        reset = "\033[0m"

        print(f"\r\n{color}[ANALYSIS] リスク: {risk_level}{reset}")

        if risk_level in ["dangerous", "critical"]:
            self.demo_stats["dangerous_commands"] += 1

            issues = safety.get("issues", [])
            if issues:
                print("  問題点:")
                for issue in issues:
                    print(f"    - {issue}")

        # 改善提案があれば表示
        improvement = result.get("improvement", {})
        if improvement.get("suggestions"):
            print("  提案:")
            for suggestion in improvement["suggestions"]:
                print(f"    - {suggestion}")

        print()  # 空行

    def _on_command_blocked(self, command: str, result: Dict[str, Any]):
        """コマンドブロック時のコールバック"""
        self.demo_stats["blocked_commands"] += 1

        print("\r\n\033[91m[BLOCKED] 危険なコマンドがブロックされました\033[0m")
        print(f"  コマンド: {command}")

        safety = result.get("safety", {})
        issues = safety.get("issues", [])
        if issues:
            print("  理由:")
            for issue in issues:
                print(f"    - {issue}")

        print()

    def _on_user_approval(self, command: str) -> bool:
        """ユーザー承認要求時のコールバック"""
        print("\r\n\033[93m[APPROVAL] このコマンドの実行には承認が必要です:\033[0m")
        print(f"  {command}")

        # デモでは自動的に拒否
        print("  → デモモードのため自動的に拒否されました")
        return False

    async def run_interactive_terminal(self):
        """インタラクティブターミナルを実行"""
        print("\n" + "=" * 60)
        print("リアルタイムコマンド解析デモ - インタラクティブモード")
        print("=" * 60)
        print("\n通常のターミナルとして使用できます。")
        print("すべてのコマンドがリアルタイムで解析されます。")
        print("\n終了するには 'exit' と入力してください。")
        print("-" * 60 + "\n")

        # PTYを作成
        master_fd, slave_fd = pty.openpty()

        # 子プロセスでシェルを起動
        pid = os.fork()

        if pid == 0:  # 子プロセス
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)

            # シェルを起動
            os.execvp("/bin/bash", ["bash", "--norc"])

        else:  # 親プロセス
            os.close(slave_fd)

            # ターミナルを生モードに設定
            self.original_tty_attrs = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin)

            try:
                await self._handle_terminal_io(master_fd)
            finally:
                # ターミナル設定を復元
                if self.original_tty_attrs:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_tty_attrs)

                # 子プロセスを終了
                os.kill(pid, 9)
                os.waitpid(pid, 0)
                os.close(master_fd)

    async def _handle_terminal_io(self, master_fd: int):
        """ターミナルI/Oを処理"""
        loop = asyncio.get_event_loop()

        # 非同期I/O用のキュー
        input_queue = asyncio.Queue()
        output_queue = asyncio.Queue()

        # I/Oタスクを開始
        input_task = asyncio.create_task(self._read_stdin(input_queue))
        output_task = asyncio.create_task(self._read_pty(master_fd, output_queue))
        process_task = asyncio.create_task(self._process_io(master_fd, input_queue, output_queue))

        try:
            # いずれかのタスクが終了するまで待機
            done, pending = await asyncio.wait(
                [input_task, output_task, process_task], return_when=asyncio.FIRST_COMPLETED
            )

            # 残りのタスクをキャンセル
            for task in pending:
                task.cancel()

        except Exception as e:
            logger.error(f"ターミナルI/O処理中にエラー: {e}")

    async def _read_stdin(self, queue: asyncio.Queue):
        """標準入力を非同期で読み取り"""
        loop = asyncio.get_event_loop()

        while True:
            try:
                # select.selectを使用して非ブロッキング読み取り
                if select.select([sys.stdin], [], [], 0)[0]:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if data:
                        await queue.put(("input", data))
                    else:
                        break
                else:
                    await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"標準入力読み取り中にエラー: {e}")
                break

    async def _read_pty(self, fd: int, queue: asyncio.Queue):
        """PTYからの出力を非同期で読み取り"""
        while True:
            try:
                # select.selectを使用して非ブロッキング読み取り
                if select.select([fd], [], [], 0)[0]:
                    data = os.read(fd, 1024)
                    if data:
                        await queue.put(("output", data))
                    else:
                        break
                else:
                    await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"PTY読み取り中にエラー: {e}")
                break

    async def _process_io(
        self, master_fd: int, input_queue: asyncio.Queue, output_queue: asyncio.Queue
    ):
        """I/Oを処理"""
        while True:
            try:
                # キューからデータを取得（タイムアウト付き）
                try:
                    io_type, data = await asyncio.wait_for(
                        asyncio.gather(
                            input_queue.get() if not input_queue.empty() else asyncio.sleep(0.01),
                            output_queue.get() if not output_queue.empty() else asyncio.sleep(0.01),
                        )[0],
                        timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    continue

                if io_type == "input":
                    # 入力をインターセプト
                    if self.interceptor:
                        processed_data = await self.interceptor.intercept_input(data)
                        if processed_data:
                            os.write(master_fd, processed_data)
                    else:
                        os.write(master_fd, data)

                elif io_type == "output":
                    # 出力を表示
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()

            except Exception as e:
                logger.error(f"I/O処理中にエラー: {e}")
                break

    def _print_demo_statistics(self):
        """デモ統計を表示"""
        print("\n" + "=" * 60)
        print("デモ統計")
        print("=" * 60)

        if self.demo_stats["start_time"] and self.demo_stats["end_time"]:
            duration = self.demo_stats["end_time"] - self.demo_stats["start_time"]
            print(f"実行時間: {duration}")

        print(f"解析したコマンド数: {self.demo_stats['commands_analyzed']}")
        print(f"危険なコマンド数: {self.demo_stats['dangerous_commands']}")
        print(f"ブロックしたコマンド数: {self.demo_stats['blocked_commands']}")

        if self.interceptor:
            interceptor_stats = self.interceptor.get_statistics()
            print(f"\n安全率: {interceptor_stats['safety_rate']:.1%}")
            print(f"ブロック率: {interceptor_stats['block_rate']:.1%}")

            # リスク分布
            session_stats = interceptor_stats.get("session_stats", {})
            risk_dist = session_stats.get("risk_distribution", {})
            if risk_dist:
                print("\nリスク分布:")
                for risk, count in risk_dist.items():
                    print(f"  {risk}: {count}件")

    async def run_demo_commands(self):
        """デモ用のコマンドシーケンスを実行"""
        print("\n" + "=" * 60)
        print("リアルタイムコマンド解析デモ - 自動実行モード")
        print("=" * 60)
        print("\n事前定義されたコマンドシーケンスを実行します。")
        print("-" * 60 + "\n")

        # デモ用コマンドシーケンス
        demo_commands = [
            ("ls -la", 1.0),
            ("ps aux | grep python", 1.5),
            ("curl https://example.com", 1.5),
            ("sudo apt update", 2.0),
            ("rm -rf /tmp/test", 2.0),
            ("chmod 777 /etc/passwd", 2.0),
            ("dd if=/dev/zero of=/dev/sda", 2.0),
            (":(){ :|:& };:", 2.0),  # フォーク爆弾
        ]

        for command, delay in demo_commands:
            print(f"\n$ {command}")

            # コマンドを解析
            if self.interceptor:
                result = await self.interceptor._analyze_command(command)

                # 解析結果の表示はコールバックで処理される

            await asyncio.sleep(delay)

        print("\n自動実行モードが完了しました。")


async def main():
    """メイン関数"""
    print("AetherTerm リアルタイムコマンド解析デモ")
    print("=" * 40)
    print("\nこのデモでは、ターミナルでのコマンド入力を")
    print("リアルタイムで解析し、危険なコマンドをブロックします。")

    demo = RealtimeCommandAnalysisDemo()

    try:
        await demo.setup()

        # デモモードを選択
        print("\nデモモードを選択してください:")
        print("1. インタラクティブモード（実際のターミナル）")
        print("2. 自動実行モード（事前定義コマンド）")

        choice = input("\n選択 (1/2): ").strip()

        if choice == "1":
            await demo.run_interactive_terminal()
        else:
            await demo.run_demo_commands()

    finally:
        await demo.teardown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nデモが中断されました。")
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()
