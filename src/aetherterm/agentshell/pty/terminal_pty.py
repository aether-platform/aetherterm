"""PTY通信コア機能

util-linux-ngのscriptコマンドと同じアーキテクチャを使用して
PTYマスター/スレーブペアでターミナル通信を管理します。
"""

import asyncio
import logging
import os
import pty
import select
import signal
import sys
from collections.abc import Awaitable
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..config import MonitorConfig
from ..domain.models import EventType, TerminalEvent
from ..utils import is_process_running

logger = logging.getLogger(__name__)


class TerminalBuffer:
    """ターミナル出力バッファ"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._buffer: List[TerminalEvent] = []
        self._current_line = b""

    def add_event(self, event: TerminalEvent) -> None:
        """イベントを追加"""
        self._buffer.append(event)

        # バッファサイズ制限
        if len(self._buffer) > self.max_size:
            self._buffer.pop(0)

    def get_recent_events(self, count: int = 10) -> List[TerminalEvent]:
        """最近のイベントを取得"""
        return self._buffer[-count:] if self._buffer else []

    def get_current_screen(self) -> str:
        """現在の画面内容を取得（簡易版）"""
        output_events = [
            event
            for event in self._buffer[-100:]  # 最近の100イベント
            if event.event_type == EventType.OUTPUT
        ]

        screen_data = b"".join(event.data for event in output_events)
        try:
            return screen_data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def clear(self) -> None:
        """バッファをクリア"""
        self._buffer.clear()
        self._current_line = b""


class TerminalPTY:
    """PTY通信クラス - scriptコマンドライクなアーキテクチャ

    scriptコマンドとの共通点:
    1. PTYマスター/スレーブペアを使用
    2. 親プロセスが入出力を監視・中継
    3. 子プロセスでシェルを実行
    4. ユーザーには透明に動作
    """

    def __init__(self, config: MonitorConfig, session_id: str):
        self.config = config
        self.session_id = session_id
        self.buffer = TerminalBuffer(config.max_history)

        # イベントコールバック
        self._event_callbacks: List[Callable[[TerminalEvent], Awaitable[None]]] = []

        # 監視状態
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._input_task: Optional[asyncio.Task] = None

        # PTYファイルディスクリプタ
        self._master_fd: Optional[int] = None
        self._slave_fd: Optional[int] = None

        # 子プロセス
        self._child_pid: Optional[int] = None

        # 統計情報
        self._stats = {
            "events_processed": 0,
            "bytes_read": 0,
            "bytes_written": 0,
            "start_time": None,
        }

    def add_event_callback(self, callback: Callable[[TerminalEvent], Awaitable[None]]) -> None:
        """イベントコールバックを追加"""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[[TerminalEvent], Awaitable[None]]) -> None:
        """イベントコールバックを削除"""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    async def start_monitoring(self, command: Optional[List[str]] = None) -> None:
        """監視を開始 - scriptコマンドライクな動作

        Args:
            command: 実行するコマンド（Noneの場合はシェルを起動）
        """
        if self._monitoring:
            logger.warning("既に監視が開始されています")
            return

        logger.info(f"PTY監視を開始します: セッション {self.session_id}")

        try:
            # PTYペアを作成（scriptと同じ）
            self._master_fd, self._slave_fd = pty.openpty()

            # 子プロセスを起動
            if command is None:
                command = [os.environ.get("SHELL", "/bin/bash")]

            self._child_pid = await self._spawn_child_process(command)

            # 監視開始
            self._monitoring = True
            self._stats["start_time"] = datetime.now()

            # 監視タスクを開始
            self._monitor_task = asyncio.create_task(self._monitor_output())
            self._input_task = asyncio.create_task(self._monitor_input())

        except Exception as e:
            logger.error(f"PTY監視の開始に失敗しました: {e}")
            await self.stop_monitoring()
            raise

    async def stop_monitoring(self) -> None:
        """監視を停止"""
        if not self._monitoring:
            return

        logger.info(f"PTY監視を停止します: セッション {self.session_id}")

        self._monitoring = False

        # 監視タスクを停止
        for task in [self._monitor_task, self._input_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._monitor_task = None
        self._input_task = None

        # 子プロセスを終了
        if self._child_pid and is_process_running(self._child_pid):
            try:
                os.kill(self._child_pid, signal.SIGTERM)
                # 少し待ってからSIGKILL
                await asyncio.sleep(1)
                if is_process_running(self._child_pid):
                    os.kill(self._child_pid, signal.SIGKILL)
            except OSError:
                pass

        # ファイルディスクリプタを閉じる
        for fd in [self._master_fd, self._slave_fd]:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        self._master_fd = None
        self._slave_fd = None
        self._child_pid = None

        # 終了イベントを送信
        exit_event = TerminalEvent(
            event_type=EventType.EXIT,
            data=b"",
            timestamp=datetime.now(),
            session_id=self.session_id,
        )
        await self._process_event(exit_event)

    async def _spawn_child_process(self, command: List[str]) -> int:
        """子プロセスを起動 - scriptコマンドと同じ方式

        Args:
            command: 実行するコマンド

        Returns:
            int: 子プロセスのPID
        """
        logger.debug(f"子プロセスを起動します: {' '.join(command)}")

        # 環境変数を準備
        env = os.environ.copy()
        env["AETHERTERM_SESSION_ID"] = self.session_id
        env["TERM"] = env.get("TERM", "xterm-256color")

        # forkして子プロセスを作成
        pid = os.fork()

        if pid == 0:
            # 子プロセス
            try:
                # スレーブPTYを標準入出力に設定
                os.dup2(self._slave_fd, 0)  # stdin
                os.dup2(self._slave_fd, 1)  # stdout
                os.dup2(self._slave_fd, 2)  # stderr

                # マスターFDを閉じる（子プロセスでは不要）
                os.close(self._master_fd)
                os.close(self._slave_fd)

                # 新しいセッションを開始
                os.setsid()

                # 制御端末を設定
                import fcntl
                import termios

                fcntl.ioctl(0, termios.TIOCSCTTY, 1)

                # コマンドを実行
                os.execvpe(command[0], command, env)

            except Exception as e:
                logger.error(f"子プロセスの実行に失敗しました: {e}")
                os._exit(1)

        else:
            # 親プロセス
            # スレーブFDを閉じる（親プロセスでは不要）
            os.close(self._slave_fd)
            self._slave_fd = None

            logger.debug(f"子プロセスを起動しました: PID {pid}")
            return pid

    async def _monitor_output(self) -> None:
        """出力監視ループ - scriptコマンドの出力処理と同等"""
        logger.debug("出力監視ループを開始します")

        try:
            while self._monitoring and self._master_fd is not None:
                # selectで読み取り可能になるまで待機
                ready, _, _ = select.select([self._master_fd], [], [], self.config.poll_interval)

                if not ready:
                    continue

                try:
                    # PTYマスターからデータを読み取り
                    data = os.read(self._master_fd, self.config.buffer_size)
                    if not data:
                        break  # EOF

                    # 標準出力にも出力（scriptと同じ動作）
                    if self.config.enable_output_capture:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()

                    # 出力イベントを作成
                    event = TerminalEvent(
                        event_type=EventType.OUTPUT,
                        data=data,
                        timestamp=datetime.now(),
                        session_id=self.session_id,
                    )

                    await self._process_event(event)
                    self._stats["bytes_read"] += len(data)

                except OSError as e:
                    if e.errno == 5:  # EIO (Input/output error) は正常終了
                        logger.debug("PTYが閉じられました")
                        break
                    logger.error(f"出力読み取りエラー: {e}")
                    break

                # 短時間待機
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.debug("出力監視ループがキャンセルされました")
            raise
        except Exception as e:
            logger.error(f"出力監視ループでエラーが発生しました: {e}")
        finally:
            logger.debug("出力監視ループを終了します")

    async def _monitor_input(self) -> None:
        """入力監視ループ - scriptコマンドの入力処理と同等"""
        logger.debug("入力監視ループを開始します")

        try:
            while self._monitoring and self._master_fd is not None:
                # 標準入力から読み取り可能になるまで待機
                ready, _, _ = select.select([sys.stdin], [], [], self.config.poll_interval)

                if not ready:
                    continue

                try:
                    # 標準入力からデータを読み取り
                    data = os.read(sys.stdin.fileno(), self.config.buffer_size)
                    if not data:
                        break  # EOF

                    # PTYマスターに書き込み
                    os.write(self._master_fd, data)

                    # 入力イベントを作成
                    if self.config.enable_input_capture:
                        event = TerminalEvent(
                            event_type=EventType.INPUT,
                            data=data,
                            timestamp=datetime.now(),
                            session_id=self.session_id,
                        )
                        await self._process_event(event)

                    self._stats["bytes_written"] += len(data)

                except OSError as e:
                    logger.error(f"入力読み取りエラー: {e}")
                    break

                # 短時間待機
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.debug("入力監視ループがキャンセルされました")
            raise
        except Exception as e:
            logger.error(f"入力監視ループでエラーが発生しました: {e}")
        finally:
            logger.debug("入力監視ループを終了します")

    async def _process_event(self, event: TerminalEvent) -> None:
        """ターミナルに入力を送信

        Args:
            data: 送信するデータ

        Returns:
            bool: 送信に成功した場合True
        """
        if not self._monitoring or self._master_fd is None:
            return False

        try:
            os.write(self._master_fd, data)

            # 入力イベントを作成
            if self.config.enable_input_capture:
                event = TerminalEvent(
                    event_type=EventType.INPUT,
                    data=data,
                    timestamp=datetime.now(),
                    session_id=self.session_id,
                )
                await self._process_event(event)

            self._stats["bytes_written"] += len(data)
            return True

        except OSError as e:
            logger.error(f"入力送信エラー: {e}")
            return False

    async def resize_terminal(self, rows: int, cols: int) -> bool:
        """ターミナルサイズを変更

        Args:
            rows: 行数
            cols: 列数

        Returns:
            bool: 変更に成功した場合True
        """
        if not self._monitoring or self._master_fd is None:
            return False

        try:
            import fcntl
            import struct
            import termios

            # TIOCSWINSZ を使用してウィンドウサイズを設定
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

            # リサイズイベントを作成
            event = TerminalEvent(
                event_type=EventType.RESIZE,
                data=b"",
                timestamp=datetime.now(),
                session_id=self.session_id,
                metadata={"rows": rows, "cols": cols},
            )
            await self._process_event(event)

            return True

        except Exception as e:
            logger.error(f"ターミナルリサイズエラー: {e}")
            return False

    def get_current_screen(self) -> str:
        """現在の画面内容を取得"""
        return self.buffer.get_current_screen()

    def get_recent_output(self, lines: int = 10) -> str:
        """最近の出力を取得"""
        events = self.buffer.get_recent_events(lines)
        output_events = [e for e in events if e.event_type == EventType.OUTPUT]

        output_data = b"".join(event.data for event in output_events)
        try:
            return output_data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        stats = self._stats.copy()
        if stats["start_time"]:
            stats["uptime"] = (datetime.now() - stats["start_time"]).total_seconds()
        return stats

    def is_monitoring(self) -> bool:
        """監視中かどうかを確認"""
        return self._monitoring

    def get_child_pid(self) -> Optional[int]:
        """子プロセスのPIDを取得"""
        return self._child_pid

    def is_child_running(self) -> bool:
        """子プロセスが実行中かどうかを確認"""
        return self._child_pid is not None and is_process_running(self._child_pid)
