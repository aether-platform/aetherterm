"""PTY Controller

PTY master/slaveを使用してログファイルを監視し、
リアルタイムでログデータを読み取る機能を提供
"""

import logging
import os
import pty
import select
import subprocess
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class PTYController:
    """PTY制御クラス"""

    def __init__(self, log_file_path: str):
        """初期化

        Args:
            log_file_path: 監視するログファイルのパス
        """
        self.log_file_path = log_file_path
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.running = False
        self.data_callback: Optional[Callable[[str], None]] = None
        self._monitor_thread = None

    def set_data_callback(self, callback: Callable[[str], None]):
        """データ受信時のコールバック関数を設定

        Args:
            callback: ログデータを受信した時に呼び出される関数
        """
        self.data_callback = callback

    def start_monitoring(self):
        """ログ監視を開始"""
        if self.running:
            logger.warning("PTY monitoring is already running")
            return

        try:
            # PTY master/slave作成
            self.master_fd, self.slave_fd = pty.openpty()

            # tail -f コマンドでログファイルを監視
            self.process = subprocess.Popen(
                ["tail", "-f", self.log_file_path],
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                stdin=subprocess.PIPE,
            )

            self.running = True

            # 監視スレッド開始
            self._monitor_thread = threading.Thread(target=self._monitor_loop)
            self._monitor_thread.daemon = True
            self._monitor_thread.start()

            logger.info(f"Started PTY monitoring for {self.log_file_path}")

        except Exception as e:
            logger.error(f"Failed to start PTY monitoring: {e}")
            self.stop_monitoring()
            raise

    def stop_monitoring(self):
        """ログ監視を停止"""
        self.running = False

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
            finally:
                self.process = None

        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception as e:
                logger.error(f"Error closing master fd: {e}")
            finally:
                self.master_fd = None

        if self.slave_fd:
            try:
                os.close(self.slave_fd)
            except Exception as e:
                logger.error(f"Error closing slave fd: {e}")
            finally:
                self.slave_fd = None

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)

        logger.info("Stopped PTY monitoring")

    def _monitor_loop(self):
        """監視ループ（別スレッドで実行）"""
        buffer = ""

        while self.running and self.master_fd:
            try:
                # selectでデータ待機（タイムアウト付き）
                ready, _, _ = select.select([self.master_fd], [], [], 1.0)

                if ready:
                    # データ読み取り
                    data = os.read(self.master_fd, 1024)
                    if data:
                        # バイトデータを文字列に変換
                        text = data.decode("utf-8", errors="ignore")
                        buffer += text

                        # 行単位で処理
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line.strip() and self.data_callback:
                                self.data_callback(line.strip())

            except OSError as e:
                if self.running:
                    logger.error(f"PTY monitoring error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")
                break

    def write_to_terminal(self, text: str):
        """ターミナルに文字列を出力

        Args:
            text: 出力する文字列
        """
        if self.master_fd:
            try:
                os.write(self.master_fd, text.encode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to write to terminal: {e}")

    def is_running(self) -> bool:
        """監視が実行中かどうかを返す"""
        return self.running

    def __enter__(self):
        """コンテキストマネージャー対応"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー対応"""
        self.stop_monitoring()
