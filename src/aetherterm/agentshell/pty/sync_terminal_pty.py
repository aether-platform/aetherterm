"""同期PTYターミナル - test.pyの機能を統合

test.pyで実装された優れたPTY通信機能を
agentshellパッケージに統合したモジュール。

主な機能:
- 同期PTY通信
- 非同期バックエンド連携
- キーワード監視
- ターミナル出力バッファリング
"""

import asyncio
import errno
import fcntl
import logging
import os
import pty
import queue
import select
import signal
import struct
import sys
import termios
import threading
import tty
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AsyncWorker:
    """非同期イベントループを管理するクラス

    メインスレッドから非同期タスクを投入し、
    別スレッドで実行するワーカー
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.queue = queue.Queue()  # タスクをキューイングするためのスレッドセーフなキュー
        self.is_running = False

    def _run_loop(self):
        """asyncioイベントループを別スレッドで実行する"""
        asyncio.set_event_loop(self.loop)
        self.is_running = True
        try:
            # キューからコルーチンを取得して実行し続ける
            while True:
                coro = self.queue.get()
                if coro is None:  # 終了シグナル
                    break
                # コルーチンをタスクとしてスケジュール
                asyncio.ensure_future(coro, loop=self.loop)
                # キューのタスクが処理されるようにイベントループを短時間実行
                self.loop.run_until_complete(
                    asyncio.sleep(0)
                )  # イベントループを一度だけ実行し、スケジュールされたタスクを処理
        finally:
            # イベントループが終了する前に残りのタスクをキャンセルしてクリーンアップ
            pending = asyncio.all_tasks(self.loop)
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()
            self.is_running = False
            logger.debug("非同期ワーカーのイベントループを終了しました")

    def start(self):
        """ワーカーを起動する"""
        if not self.thread.is_alive():
            self.thread.start()
            # イベントループが完全に起動するのを少し待つ
            while not self.is_running:
                import time

                time.sleep(0.01)
            logger.debug("非同期ワーカーを起動しました")

    def stop(self):
        """ワーカーを停止する"""
        if self.thread.is_alive():
            # キューに終了シグナルを送信
            self.queue.put_nowait(None)
            self.thread.join(timeout=5)  # スレッドが終了するのを待つ
            if self.thread.is_alive():
                logger.warning("非同期ワーカーのスレッドが正常に終了しませんでした")

    def run_async_task(self, coro):
        """メインスレッドから非同期タスクを投入する"""
        if self.is_running:
            # コルーチンをキューに入れて、イベントループスレッドで実行されるのを待つ
            self.queue.put_nowait(coro)
        else:
            logger.warning("非同期ワーカーが実行されていません。タスクは投入されませんでした")


class TerminalUtils:
    """ターミナル操作のユーティリティ関数"""

    @staticmethod
    def set_raw_mode(fd: int) -> Optional[Any]:
        """ファイルディスクリプタをRAWモードに設定する"""
        try:
            old_settings = termios.tcgetattr(fd)
            tty.setraw(fd)
            return old_settings
        except termios.error as e:
            logger.error(f"RAWモード設定エラー: {e}")
            return None

    @staticmethod
    def restore_terminal_mode(fd: int, settings: Any) -> None:
        """ターミナルモードを元に戻す"""
        if settings:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, settings)
            except termios.error as e:
                logger.error(f"ターミナルモード復元エラー (fd {fd}): {e}")


class SyncTerminalPTY:
    """同期PTYターミナル - test.pyの機能を統合

    既存のTerminalPTYクラスとは異なり、
    同期的なPTY処理と非同期バックエンドの組み合わせを提供
    """

    def __init__(
        self,
        session_id: str,
        keywords_to_monitor: Optional[List[str]] = None,
        async_log_callback: Optional[Callable[[str], Any]] = None,
    ):
        self.session_id = session_id
        self.keywords_to_monitor = keywords_to_monitor or ["error", "warning", "fail"]
        self.async_log_callback = async_log_callback

        # 非同期ワーカー
        self.async_worker = AsyncWorker()

        # PTY関連
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.child_pid: Optional[int] = None

        # ターミナル設定
        self.old_terminal_attrs: Optional[Any] = None

        # 出力バッファ
        self.output_buffer: List[str] = []

        # 統計情報
        self.stats = {
            "bytes_read": 0,
            "bytes_written": 0,
            "keywords_detected": 0,
            "lines_processed": 0,
        }

    def start_shell(self, shell_command: Optional[str] = None) -> None:
        """PTYを介して対話型シェルを起動し、非同期バックエンドと連携する

        Args:
            shell_command: 実行するシェルコマンド（Noneの場合は環境変数SHELLを使用）
        """
        logger.info(f"PTYシェルを起動します: セッション {self.session_id}")

        # 非同期ワーカーを起動
        self.async_worker.start()

        try:
            # PTYペアを作成
            self.master_fd, self.slave_fd = pty.openpty()

            # ターミナルをRAWモードに設定
            self.old_terminal_attrs = TerminalUtils.set_raw_mode(sys.stdin.fileno())
            if self.old_terminal_attrs is None:
                raise RuntimeError("ターミナルのRAWモード設定に失敗しました")

            # 子プロセスを起動
            self.child_pid = os.fork()

            if self.child_pid == 0:  # 子プロセス
                self._setup_child_process(shell_command)
            else:  # 親プロセス
                self._run_parent_process()

        except Exception as e:
            logger.error(f"PTYシェルの起動に失敗しました: {e}")
            self.cleanup()
            raise
        finally:
            self.cleanup()

    def _setup_child_process(self, shell_command: Optional[str]) -> None:
        """子プロセスの設定"""
        try:
            # マスターFDを閉じる
            os.close(self.master_fd)

            # スレーブPTYを標準入出力に設定
            os.dup2(self.slave_fd, sys.stdin.fileno())
            os.dup2(self.slave_fd, sys.stdout.fileno())
            os.dup2(self.slave_fd, sys.stderr.fileno())
            os.close(self.slave_fd)

            # 新しいセッションを開始
            os.setsid()

            # 制御端末を設定
            try:
                fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSCTTY, 0)
            except Exception as e:
                logger.warning(f"制御端末の設定に失敗しました: {e}")

            # シェルを実行
            shell = shell_command or os.environ.get("SHELL", "/bin/bash")
            try:
                os.execv(shell, [shell, "-i"])
            except FileNotFoundError:
                logger.error(f"シェル '{shell}' が見つかりません")
                os._exit(1)
            except Exception as e:
                logger.error(f"シェル '{shell}' の実行に失敗しました: {e}")
                os._exit(1)

        except Exception as e:
            logger.error(f"子プロセスの設定に失敗しました: {e}")
            os._exit(1)

    def _run_parent_process(self) -> None:
        """親プロセスのメインループ"""
        # スレーブFDを閉じる
        os.close(self.slave_fd)
        self.slave_fd = None

        # SIGWINCH (ターミナルサイズ変更) ハンドラ
        def handle_winch(signum, frame):
            try:
                buf = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
                ws = struct.unpack("HHHH", buf)
                rows, cols = ws[0], ws[1]
                pty.set_terminal_size(self.master_fd, rows, cols)
                logger.debug(f"ターミナルサイズを変更しました: {rows}x{cols}")
            except Exception as e:
                logger.warning(f"SIGWINCH処理エラー: {e}")

        signal.signal(signal.SIGWINCH, handle_winch)

        try:
            while True:
                # select.select にタイムアウトを設定し、子プロセスの終了チェックも定期的に行う
                rlist, _, _ = select.select([sys.stdin.fileno(), self.master_fd], [], [], 0.1)

                # ユーザーからの入力
                if sys.stdin.fileno() in rlist:
                    input_data = os.read(sys.stdin.fileno(), 4096)
                    if not input_data:  # EOF (Ctrl+D)
                        break
                    os.write(self.master_fd, input_data)
                    self.stats["bytes_written"] += len(input_data)

                # PTYマスターから出力 (シェルからの出力)
                if self.master_fd in rlist:
                    try:
                        output_data = os.read(self.master_fd, 4096)
                        if not output_data:  # EOF (子プロセスが終了)
                            break

                        # 標準出力に書き込み
                        sys.stdout.buffer.write(output_data)
                        sys.stdout.flush()
                        self.stats["bytes_read"] += len(output_data)

                        # 出力データを監視
                        self._process_output(output_data)

                    except OSError as e:
                        if e.errno == errno.EIO:  # Input/output error (FD closed)
                            break
                        raise

                # 子プロセスが終了したかチェック
                try:
                    pid, status = os.waitpid(self.child_pid, os.WNOHANG)
                    if pid == self.child_pid:  # 子プロセスが終了
                        logger.info(
                            f"子プロセス (PID: {self.child_pid}) が終了しました。ステータス: {status}"
                        )
                        break
                except ChildProcessError:  # 子プロセスが既に終了している場合
                    break

        except InterruptedError:
            logger.info("セッションがシグナルによって中断されました")
        except Exception as e:
            logger.error(f"メインループでエラーが発生しました: {e}")

    def _process_output(self, output_data: bytes) -> None:
        """出力データを処理し、キーワード監視を行う"""
        try:
            # 出力データをテキストに変換
            output_text = output_data.decode("utf-8", errors="ignore")
            self.output_buffer.append(output_text)

            # バッファされた行を結合して監視
            full_output_line = "".join(self.output_buffer)
            if "\n" in full_output_line:
                lines = full_output_line.splitlines(keepends=True)
                for i, line in enumerate(lines):
                    if not line.endswith("\n") and i == len(lines) - 1:
                        # 最後の行が不完全なら残しておく
                        self.output_buffer = [line]
                        break
                    # 完全な行を処理
                    self._check_keywords_in_line(line)
                    self.stats["lines_processed"] += 1
                else:
                    # 全ての行が処理された
                    self.output_buffer = []  # バッファをクリア

        except Exception as e:
            logger.error(f"出力処理エラー: {e}")

    def _check_keywords_in_line(self, line: str) -> None:
        """行内のキーワードをチェック"""
        for keyword in self.keywords_to_monitor:
            if keyword in line.lower():
                logger.info(f"キーワード '{keyword}' を検出: {line.strip()}")
                self.stats["keywords_detected"] += 1

                # 非同期ログタスクを投入
                if self.async_log_callback:
                    self.async_worker.run_async_task(
                        self.async_log_callback(f"検出: '{keyword}' - {line.strip()}")
                    )
                break

    def cleanup(self) -> None:
        """リソースのクリーンアップ"""
        logger.debug("PTYシェルのクリーンアップを開始します")

        # ターミナルモードを復元
        if self.old_terminal_attrs:
            TerminalUtils.restore_terminal_mode(sys.stdin.fileno(), self.old_terminal_attrs)
            self.old_terminal_attrs = None

        # ファイルディスクリプタを閉じる
        for fd_name, fd in [("master_fd", self.master_fd), ("slave_fd", self.slave_fd)]:
            if fd is not None:
                try:
                    os.close(fd)
                    logger.debug(f"{fd_name} を閉じました")
                except OSError as e:
                    if e.errno != errno.EBADF:  # Bad file descriptor 以外ならログ
                        logger.warning(f"{fd_name} のクローズエラー: {e}")

        self.master_fd = None
        self.slave_fd = None

        # 子プロセスの終了を待機
        if self.child_pid is not None:
            try:
                os.waitpid(self.child_pid, 0)
                logger.debug(f"子プロセス (PID: {self.child_pid}) の終了を確認しました")
            except ChildProcessError:
                pass
            self.child_pid = None

        # 非同期ワーカーを停止
        self.async_worker.stop()

        logger.info("PTYシェルのクリーンアップが完了しました")

    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        return self.stats.copy()

    def is_running(self) -> bool:
        """シェルが実行中かどうかを確認"""
        return self.child_pid is not None


# デフォルトの非同期ログ関数
async def default_async_log(message: str) -> None:
    """デフォルトの非同期ログ処理

    Args:
        message: ログメッセージ
    """
    logger.info(f"[ASYNC LOG] 処理中: '{message[:50]}...'")
    await asyncio.sleep(1)  # 実際のI/Oや計算をシミュレート
    logger.info(f"[ASYNC LOG] 完了: '{message[:50]}...'")


def run_shell_with_async_backend(
    session_id: str = "default",
    keywords_to_monitor: Optional[List[str]] = None,
    shell_command: Optional[str] = None,
    async_log_callback: Optional[Callable[[str], Any]] = None,
) -> None:
    """PTYを介して対話型シェルを起動し、非同期バックエンドと連携する

    Args:
        session_id: セッションID
        keywords_to_monitor: 監視するキーワードのリスト
        shell_command: 実行するシェルコマンド
        async_log_callback: 非同期ログコールバック関数
    """
    logger.info("PTYシェル（非同期バックエンド連携）を開始します")

    # デフォルトのコールバックを設定
    if async_log_callback is None:
        async_log_callback = default_async_log

    # PTYシェルを作成・実行
    pty_shell = SyncTerminalPTY(
        session_id=session_id,
        keywords_to_monitor=keywords_to_monitor,
        async_log_callback=async_log_callback,
    )

    try:
        pty_shell.start_shell(shell_command)
    finally:
        # 統計情報を表示
        stats = pty_shell.get_stats()
        logger.info(f"セッション統計: {stats}")
        logger.info("PTYシェルが終了しました")


if __name__ == "__main__":
    # テスト実行
    logging.basicConfig(level=logging.INFO)
    run_shell_with_async_backend()
