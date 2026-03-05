"""PTY Monitor Main

PTYログ監視とAI解析による自動ブロック機能のメインエントリーポイント
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from .ai_analyzer import AIAnalyzer, AnalysisResult
from .input_blocker import InputBlocker
from .pty_controller import PTYController

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PTYMonitor:
    """PTY監視メインクラス"""

    def __init__(self, log_file_path: str, ai_server_url: str = "ws://localhost:8765"):
        """初期化

        Args:
            log_file_path: 監視するログファイルのパス
            ai_server_url: AIサーバーのWebSocket URL
        """
        self.log_file_path = log_file_path
        self.ai_server_url = ai_server_url

        # コンポーネント初期化
        self.pty_controller = PTYController(log_file_path)
        self.ai_analyzer = AIAnalyzer(ai_server_url)
        self.input_blocker = InputBlocker()

        self.running = False
        self.stats = {
            "total_lines": 0,
            "safe_lines": 0,
            "medium_lines": 0,
            "high_lines": 0,
            "critical_lines": 0,
            "blocked_count": 0,
        }

    async def start(self):
        """監視開始"""
        if self.running:
            logger.warning("PTY Monitor is already running")
            return

        logger.info(f"Starting PTY Monitor for {self.log_file_path}")

        try:
            # シグナルハンドラー設定
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # AIサーバーに接続
            await self.ai_analyzer.connect_to_ai_server()

            # コールバック設定
            self.pty_controller.set_data_callback(self._on_log_data)
            self.input_blocker.set_unblock_callback(self._on_unblock)

            # 各コンポーネント開始
            self.input_blocker.start_monitoring()
            self.pty_controller.start_monitoring()

            self.running = True
            logger.info("PTY Monitor started successfully")

            # メインループ
            await self._main_loop()

        except Exception as e:
            logger.error(f"Failed to start PTY Monitor: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """監視停止"""
        if not self.running:
            return

        logger.info("Stopping PTY Monitor...")
        self.running = False

        # 各コンポーネント停止
        try:
            self.pty_controller.stop_monitoring()
        except Exception as e:
            logger.error(f"Error stopping PTY controller: {e}")

        try:
            self.input_blocker.stop_monitoring()
        except Exception as e:
            logger.error(f"Error stopping input blocker: {e}")

        try:
            await self.ai_analyzer.disconnect_from_ai_server()
        except Exception as e:
            logger.error(f"Error disconnecting from AI server: {e}")

        # 統計情報表示
        self._display_stats()
        logger.info("PTY Monitor stopped")

    def _on_log_data(self, log_line: str):
        """ログデータ受信時のコールバック

        Args:
            log_line: 受信したログ行
        """
        # 非同期解析をスケジュール
        asyncio.create_task(self._analyze_log_line(log_line))

    async def _analyze_log_line(self, log_line: str):
        """ログ行の解析処理

        Args:
            log_line: 解析するログ行
        """
        try:
            self.stats["total_lines"] += 1

            # AI解析実行
            result = await self.ai_analyzer.analyze_log_line(log_line)

            # 統計更新
            self._update_stats(result)

            # ログ出力
            logger.info(f"Log analyzed: {result.threat_level.value} - {log_line[:50]}...")

            if result.detected_keywords:
                logger.warning(f"Detected keywords: {result.detected_keywords}")

            # ブロック判定
            if result.should_block and not self.input_blocker.is_blocked():
                self.stats["blocked_count"] += 1
                self.input_blocker.block_input(result.message)
                logger.critical(f"INPUT BLOCKED: {result.message}")

        except Exception as e:
            logger.error(f"Error analyzing log line: {e}")

    def _update_stats(self, result: AnalysisResult):
        """統計情報更新

        Args:
            result: 解析結果
        """
        threat_level = result.threat_level.value
        if threat_level == "safe":
            self.stats["safe_lines"] += 1
        elif threat_level == "medium":
            self.stats["medium_lines"] += 1
        elif threat_level == "high":
            self.stats["high_lines"] += 1
        elif threat_level == "critical":
            self.stats["critical_lines"] += 1

    def _on_unblock(self):
        """ブロック解除時のコールバック"""
        logger.info("Input unblocked by user confirmation")

    def _signal_handler(self, signum, frame):
        """シグナルハンドラー"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def _main_loop(self):
        """メインループ"""
        last_stats_time = time.time()

        while self.running:
            try:
                await asyncio.sleep(1)

                # 定期的に統計情報を表示（60秒間隔）
                current_time = time.time()
                if current_time - last_stats_time >= 60:
                    self._display_stats()
                    last_stats_time = current_time

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

    def _display_stats(self):
        """統計情報表示"""
        total = self.stats["total_lines"]
        if total == 0:
            logger.info("No log lines processed yet")
            return

        safe_pct = (self.stats["safe_lines"] / total) * 100
        medium_pct = (self.stats["medium_lines"] / total) * 100
        high_pct = (self.stats["high_lines"] / total) * 100
        critical_pct = (self.stats["critical_lines"] / total) * 100

        stats_msg = f"""
PTY Monitor Statistics:
  Total lines processed: {total}
  Safe: {self.stats["safe_lines"]} ({safe_pct:.1f}%)
  Medium threat: {self.stats["medium_lines"]} ({medium_pct:.1f}%)
  High threat: {self.stats["high_lines"]} ({high_pct:.1f}%)
  Critical threat: {self.stats["critical_lines"]} ({critical_pct:.1f}%)
  Times blocked: {self.stats["blocked_count"]}
  Currently blocked: {"Yes" if self.input_blocker.is_blocked() else "No"}
"""
        logger.info(stats_msg)


async def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="PTY Log Monitor with AI Analysis and Auto-blocking"
    )
    parser.add_argument("--log-file", required=True, help="Path to the log file to monitor")
    parser.add_argument(
        "--ai-server-url",
        default="ws://localhost:8765",
        help="AI server WebSocket URL (default: ws://localhost:8765)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--create-test-log", action="store_true", help="Create a test log file for demonstration"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # テストログファイル作成
    if args.create_test_log:
        await create_test_log_file(args.log_file)
        return

    # ログファイル存在確認
    log_path = Path(args.log_file)
    if not log_path.exists():
        logger.error(f"Log file does not exist: {args.log_file}")
        logger.info("Use --create-test-log to create a test log file")
        sys.exit(1)

    # PTY Monitor開始
    monitor = PTYMonitor(args.log_file, args.ai_server_url)

    try:
        await monitor.start()
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Monitor error: {e}")
        sys.exit(1)


async def create_test_log_file(log_file_path: str):
    """テスト用ログファイルを作成

    Args:
        log_file_path: 作成するログファイルのパス
    """
    test_log_content = """2025-06-18 12:00:01 INFO: System startup completed
2025-06-18 12:00:02 INFO: User login: testuser
2025-06-18 12:00:03 INFO: Command executed: ls -la
2025-06-18 12:00:04 INFO: Command executed: ps aux
2025-06-18 12:00:05 WARN: Command executed: sudo systemctl status
2025-06-18 12:00:06 INFO: Command executed: cat /etc/passwd
2025-06-18 12:00:07 CRITICAL: Command executed: sudo rm -rf /tmp/test
2025-06-18 12:00:08 INFO: Command executed: pwd
2025-06-18 12:00:09 INFO: Command executed: whoami
2025-06-18 12:00:10 INFO: Normal operation continues
"""

    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as f:
        f.write(test_log_content)

    logger.info(f"Test log file created: {log_file_path}")
    logger.info("You can now run the monitor with:")
    logger.info(
        f"  python -m src.aetherterm.agentshell.pty_monitor.main --log-file {log_file_path}"
    )


if __name__ == "__main__":
    asyncio.run(main())
