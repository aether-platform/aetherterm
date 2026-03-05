"""AsyncPTY - asyncioベースのPTY管理

PTYをオープンしてbash(またはオーバーライドコマンド)を起動し、
asyncioイベントループでI/Oを中継する。
"""

import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import sys
import termios
from enum import Enum, auto
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class InputMode(Enum):
    """入力モード"""

    NORMAL = auto()  # ユーザー入力をそのままPTYへ
    BLOCKED = auto()  # ユーザー入力を無視
    REMOTE = auto()  # ZMQ経由のリモート入力のみ受付


class AsyncPTY:
    """asyncioベースのPTY管理クラス

    - デフォルトbash、コマンドオーバーライド可能
    - InputModeで入力制御
    - write_input()でプログラムからの入力注入
    - 出力コールバックで外部配信
    """

    def __init__(
        self,
        command: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        rows: int = 24,
        cols: int = 80,
    ):
        self._command = command or [os.environ.get("SHELL", "/bin/bash")]
        self._env = env
        self._rows = rows
        self._cols = cols

        self._master_fd: Optional[int] = None
        self._child_pid: Optional[int] = None
        self._running = False
        self._input_mode = InputMode.NORMAL

        # コールバック
        self._on_output: Optional[Callable[[bytes], None]] = None
        self._on_exit: Optional[Callable[[int], None]] = None

        # asyncio
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._child_watcher_task: Optional[asyncio.Task] = None

        # 元のターミナル設定(stdin用)
        self._orig_termios = None

    @property
    def input_mode(self) -> InputMode:
        return self._input_mode

    @input_mode.setter
    def input_mode(self, mode: InputMode) -> None:
        old = self._input_mode
        self._input_mode = mode
        logger.info(f"Input mode: {old.name} -> {mode.name}")
        if mode == InputMode.NORMAL:
            self._start_stdin_reader()
        else:
            self._stop_stdin_reader()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def child_pid(self) -> Optional[int]:
        return self._child_pid

    def set_on_output(self, callback: Callable[[bytes], None]) -> None:
        """PTY出力コールバック (ZMQ配信用等)"""
        self._on_output = callback

    def set_on_exit(self, callback: Callable[[int], None]) -> None:
        """子プロセス終了コールバック"""
        self._on_exit = callback

    async def start(self) -> None:
        """PTYを開いて子プロセスを起動"""
        if self._running:
            return

        self._loop = asyncio.get_running_loop()

        # PTYペア作成
        master_fd, slave_fd = pty.openpty()

        # ターミナルサイズ設定
        winsize = struct.pack("HHHH", self._rows, self._cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        # 環境変数
        env = self._env or os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env["AETHERTERM_EXPERIMENTAL"] = "1"

        # fork
        pid = os.fork()

        if pid == 0:
            # --- 子プロセス ---
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            os.close(slave_fd)
            fcntl.ioctl(0, termios.TIOCSCTTY, 1)
            os.execvpe(self._command[0], self._command, env)
            # execvpeが失敗した場合
            os._exit(1)
        else:
            # --- 親プロセス ---
            os.close(slave_fd)
            self._master_fd = master_fd
            self._child_pid = pid
            self._running = True

            # master fdをnon-blockingに
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # PTY出力の監視を開始 (add_reader)
            self._loop.add_reader(master_fd, self._on_master_readable)

            # stdin読み取り開始 (NORMALモードのとき)
            if self._input_mode == InputMode.NORMAL:
                self._start_stdin_reader()

            # 子プロセス監視
            self._child_watcher_task = asyncio.create_task(self._watch_child())

            logger.info(
                f"PTY started: pid={pid}, cmd={self._command}, "
                f"size={self._rows}x{self._cols}"
            )

    async def stop(self) -> None:
        """PTYを閉じて子プロセスを終了"""
        if not self._running:
            return
        self._running = False

        # reader解除
        if self._master_fd is not None:
            try:
                self._loop.remove_reader(self._master_fd)
            except Exception:
                pass
        self._stop_stdin_reader()

        # ターミナル設定復元
        self._restore_termios()

        # watcher停止
        if self._child_watcher_task:
            self._child_watcher_task.cancel()
            try:
                await self._child_watcher_task
            except asyncio.CancelledError:
                pass

        # 子プロセス終了
        if self._child_pid is not None:
            try:
                os.kill(self._child_pid, signal.SIGTERM)
                await asyncio.sleep(0.5)
                try:
                    os.waitpid(self._child_pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            except ProcessLookupError:
                pass
            self._child_pid = None

        # master fd閉じる
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        logger.info("PTY stopped")

    async def write_input(self, data: bytes) -> bool:
        """PTYに入力を書き込む (プログラムから / ZMQリモートから)

        InputModeに関係なく常に書き込み可能。
        ユーザーのstdinとは独立した入力経路。
        """
        if not self._running or self._master_fd is None:
            return False
        try:
            os.write(self._master_fd, data)
            return True
        except OSError as e:
            logger.error(f"Write error: {e}")
            return False

    async def resize(self, rows: int, cols: int) -> bool:
        """ターミナルサイズ変更"""
        if not self._running or self._master_fd is None:
            return False
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
            self._rows = rows
            self._cols = cols
            # SIGWINCHを子プロセスに送信
            if self._child_pid:
                os.kill(self._child_pid, signal.SIGWINCH)
            return True
        except OSError as e:
            logger.error(f"Resize error: {e}")
            return False

    # ---- Internal ----

    def _on_master_readable(self) -> None:
        """PTYマスターにデータ到着 (add_readerコールバック)"""
        try:
            data = os.read(self._master_fd, 65536)
            if not data:
                # EOF
                asyncio.ensure_future(self.stop())
                return
            # コールバック通知
            if self._on_output:
                self._on_output(data)
        except OSError as e:
            if e.errno == 5:  # EIO - 子プロセス終了
                asyncio.ensure_future(self.stop())
            else:
                logger.error(f"Master read error: {e}")

    def _on_stdin_readable(self) -> None:
        """stdinにデータ到着 (NORMALモード時のみアクティブ)"""
        if self._input_mode != InputMode.NORMAL:
            # drain stdin
            try:
                os.read(sys.stdin.fileno(), 4096)
            except OSError:
                pass
            return

        try:
            data = os.read(sys.stdin.fileno(), 4096)
            if data and self._master_fd is not None:
                os.write(self._master_fd, data)
        except OSError as e:
            logger.error(f"Stdin read error: {e}")

    def _start_stdin_reader(self) -> None:
        """stdinのadd_readerを登録"""
        if self._loop is None:
            return
        try:
            # raw modeに設定
            if sys.stdin.isatty():
                self._orig_termios = termios.tcgetattr(sys.stdin)
                import tty

                tty.setraw(sys.stdin.fileno())
            self._loop.add_reader(sys.stdin.fileno(), self._on_stdin_readable)
        except Exception as e:
            logger.warning(f"Cannot add stdin reader: {e}")

    def _stop_stdin_reader(self) -> None:
        """stdinのadd_readerを解除"""
        if self._loop is None:
            return
        try:
            self._loop.remove_reader(sys.stdin.fileno())
        except Exception:
            pass

    def _restore_termios(self) -> None:
        """ターミナル設定復元"""
        if self._orig_termios and sys.stdin.isatty():
            try:
                termios.tcsetattr(
                    sys.stdin, termios.TCSADRAIN, self._orig_termios
                )
            except Exception:
                pass
            self._orig_termios = None

    async def _watch_child(self) -> None:
        """子プロセスの終了を監視"""
        try:
            while self._running and self._child_pid is not None:
                try:
                    pid, status = os.waitpid(self._child_pid, os.WNOHANG)
                    if pid != 0:
                        exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                        logger.info(f"Child exited: pid={pid}, status={exit_code}")
                        if self._on_exit:
                            self._on_exit(exit_code)
                        await self.stop()
                        return
                except ChildProcessError:
                    return
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
