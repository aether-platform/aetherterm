"""PTY Chaining ミドルウェア

AsyncioTerminalとOS Shellの間にAgentShellをPTYミドルウェアとして挟みます。

アーキテクチャ:
    AsyncioTerminal                   AgentShell Process                OS Shell
         │                                  │                              │
    PTY1 master ──── PTY1 slave = stdin/stdout/stderr                      │
         │                   │                                             │
         │              I/O Monitor ←→ AI Analyzer                         │
         │                   │                │                            │
         │              Command Filter   ZMQ DEALER (to Broker)            │
         │                   │                                             │
         │              PTY2 master ──── PTY2 slave = stdin/stdout/stderr
         │                                                                 │

データフロー:
1. ユーザー入力 → PTY1 slave(stdin) → _relay_user_to_shell() → input_filter → PTY2 master → OS Shell
2. OS Shell出力 → PTY2 slave(stdout) → PTY2 master → _relay_shell_to_user() → output_filter → PTY1 slave(stdout) → AsyncioTerminal → Frontend
3. 全I/OはZMQ PUB/SUBでイベント配信（他Agentが監視可能）
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
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Filter function type: (data: bytes) -> Optional[bytes]
# Returns None to suppress, modified bytes to transform, or original to pass through
FilterFn = Callable[[bytes], Optional[bytes]]


class PTYChain:
    """PTY二重チェーン

    stdin/stdout がPTY1 slaveに接続された状態で起動される。
    PTY2を作成してOS Shellを起動し、両者の間でI/Oを中継する。
    """

    def __init__(self):
        self._pty2_master: Optional[int] = None
        self._child_pid: Optional[int] = None
        self._running = False

        # I/Oフィルター
        self._input_filter: Optional[FilterFn] = None
        self._output_filter: Optional[FilterFn] = None

        # I/Oコールバック（ZMQ配信用）
        self._on_user_input: Optional[Callable[[bytes], None]] = None
        self._on_shell_output: Optional[Callable[[bytes], None]] = None

        # Relay tasks
        self._relay_tasks: List[asyncio.Task] = []

    async def start(self, shell_cmd: Optional[List[str]] = None) -> None:
        """PTYチェーンを開始

        Args:
            shell_cmd: OS Shellコマンド (デフォルト: [$SHELL, "-il"])
        """
        if self._running:
            return

        if shell_cmd is None:
            shell = os.environ.get("SHELL", "/bin/bash")
            shell_cmd = [shell, "-il"]

        # PTY2を作成
        master_fd, slave_fd = pty.openpty()
        self._pty2_master = master_fd

        # ターミナルサイズをPTY1からPTY2に同期
        try:
            winsize = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except (OSError, ValueError):
            # stdinがTTYでない場合はデフォルトサイズを使用
            s = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, s)

        # Fork
        pid = os.fork()

        if pid == 0:
            # Child process: OS Shellを起動
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            os.close(slave_fd)

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"

            os.execvpe(shell_cmd[0], shell_cmd, env)
        else:
            # Parent process
            self._child_pid = pid
            os.close(slave_fd)

            # PTY2 masterをnon-blockingに設定
            fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)

            self._running = True

            # I/O relayタスクを開始
            self._relay_tasks = [
                asyncio.create_task(self._relay_user_to_shell()),
                asyncio.create_task(self._relay_shell_to_user()),
                asyncio.create_task(self._monitor_child()),
            ]

            logger.info(f"PTY Chain started (child PID={pid}, shell={shell_cmd})")

    async def stop(self) -> None:
        """PTYチェーンを停止"""
        if not self._running:
            return

        self._running = False

        # Relayタスクを停止
        for task in self._relay_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._relay_tasks.clear()

        # PTY2 masterを閉じる
        if self._pty2_master is not None:
            try:
                os.close(self._pty2_master)
            except OSError:
                pass
            self._pty2_master = None

        # 子プロセスを終了
        if self._child_pid is not None:
            try:
                os.kill(self._child_pid, signal.SIGTERM)
                for _ in range(50):
                    try:
                        pid, status = os.waitpid(self._child_pid, os.WNOHANG)
                        if pid != 0:
                            break
                    except OSError:
                        break
                    await asyncio.sleep(0.1)
                else:
                    try:
                        os.kill(self._child_pid, signal.SIGKILL)
                        os.waitpid(self._child_pid, 0)
                    except OSError:
                        pass
            except OSError:
                pass
            self._child_pid = None

        logger.info("PTY Chain stopped")

    async def inject_command(self, command: str) -> None:
        """Agent → OS Shell にコマンドを注入

        Args:
            command: 実行するコマンド（改行は自動付加）
        """
        if not self._running or self._pty2_master is None:
            return

        data = command.encode("utf-8")
        if not data.endswith(b"\n"):
            data += b"\n"

        try:
            await asyncio.get_event_loop().run_in_executor(None, os.write, self._pty2_master, data)
            logger.debug(f"Command injected: {command.strip()}")
        except OSError as e:
            logger.error(f"Command inject error: {e}")

    async def inject_output(self, output: str) -> None:
        """Agent → ユーザー表示（PTY1 stdout経由）

        Args:
            output: ユーザーに表示する文字列
        """
        if not self._running:
            return

        data = output.encode("utf-8")
        try:
            await asyncio.get_event_loop().run_in_executor(None, sys.stdout.buffer.write, data)
            sys.stdout.buffer.flush()
        except OSError as e:
            logger.error(f"Output inject error: {e}")

    def set_input_filter(self, filter_fn: FilterFn) -> None:
        """ユーザー入力フィルターを設定"""
        self._input_filter = filter_fn

    def set_output_filter(self, filter_fn: FilterFn) -> None:
        """Shell出力フィルターを設定"""
        self._output_filter = filter_fn

    def set_on_user_input(self, callback: Callable[[bytes], None]) -> None:
        """ユーザー入力コールバックを設定（ZMQ配信用）"""
        self._on_user_input = callback

    def set_on_shell_output(self, callback: Callable[[bytes], None]) -> None:
        """Shell出力コールバックを設定（ZMQ配信用）"""
        self._on_shell_output = callback

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def child_pid(self) -> Optional[int]:
        return self._child_pid

    # ---- Internal relay ----

    async def _relay_user_to_shell(self) -> None:
        """ユーザー入力をOS Shellに中継
        stdin (PTY1 slave) → filter → PTY2 master
        """
        loop = asyncio.get_event_loop()
        try:
            while self._running and self._pty2_master is not None:
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, self._read_stdin),
                        timeout=0.1,
                    )
                    if not data:
                        continue

                    # コールバック通知
                    if self._on_user_input:
                        try:
                            if asyncio.iscoroutinefunction(self._on_user_input):
                                await self._on_user_input(data)
                            else:
                                self._on_user_input(data)
                        except Exception as e:
                            logger.error(f"User input callback error: {e}")

                    # フィルター適用
                    if self._input_filter:
                        filtered = self._input_filter(data)
                        if filtered is None:
                            continue  # 入力を抑制
                        data = filtered

                    # PTY2 masterに書き込み
                    await loop.run_in_executor(None, os.write, self._pty2_master, data)

                except asyncio.TimeoutError:
                    continue
                except OSError:
                    break
        except asyncio.CancelledError:
            pass

    async def _relay_shell_to_user(self) -> None:
        """OS Shell出力をユーザーに中継
        PTY2 master → filter → stdout (PTY1 slave)
        """
        loop = asyncio.get_event_loop()
        try:
            while self._running and self._pty2_master is not None:
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, self._read_pty2),
                        timeout=0.1,
                    )
                    if not data:
                        continue

                    # コールバック通知
                    if self._on_shell_output:
                        try:
                            if asyncio.iscoroutinefunction(self._on_shell_output):
                                await self._on_shell_output(data)
                            else:
                                self._on_shell_output(data)
                        except Exception as e:
                            logger.error(f"Shell output callback error: {e}")

                    # フィルター適用
                    if self._output_filter:
                        filtered = self._output_filter(data)
                        if filtered is None:
                            continue  # 出力を抑制
                        data = filtered

                    # stdout (PTY1 slave) に書き込み
                    await loop.run_in_executor(None, self._write_stdout, data)

                except asyncio.TimeoutError:
                    continue
                except OSError:
                    break
        except asyncio.CancelledError:
            pass

    async def _monitor_child(self) -> None:
        """子プロセスの終了を監視"""
        try:
            while self._running and self._child_pid is not None:
                try:
                    pid, status = os.waitpid(self._child_pid, os.WNOHANG)
                    if pid != 0:
                        logger.info(f"Child process {self._child_pid} exited (status={status})")
                        self._running = False
                        break
                except OSError:
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    def _read_stdin(self) -> bytes:
        """stdinから読み込み（blocking executor用）"""
        try:
            return os.read(sys.stdin.fileno(), 4096)
        except OSError:
            return b""

    def _read_pty2(self) -> bytes:
        """PTY2 masterから読み込み（blocking executor用）"""
        try:
            return os.read(self._pty2_master, 4096)
        except OSError:
            return b""

    @staticmethod
    def _write_stdout(data: bytes) -> None:
        """stdoutに書き込み"""
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
