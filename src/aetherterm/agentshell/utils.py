"""ユーティリティモジュール

ラッパープログラム全体で使用される共通機能を提供します。
"""

import asyncio
import logging
import os
import signal
import time
import uuid
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """ユニークなセッションIDを生成

    Returns:
        str: セッションID
    """
    return str(uuid.uuid4())


def get_terminal_size() -> tuple[int, int]:
    """現在のターミナルサイズを取得

    Returns:
        tuple[int, int]: (行数, 列数)
    """
    try:
        import shutil

        size = shutil.get_terminal_size()
        return size.lines, size.columns
    except Exception:
        return 24, 80  # デフォルトサイズ


def is_process_running(pid: int) -> bool:
    """指定されたPIDのプロセスが実行中かチェック

    Args:
        pid: プロセスID

    Returns:
        bool: プロセスが実行中の場合True
    """
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def safe_kill_process(pid: int, timeout: int = 5) -> bool:
    """プロセスを安全に終了させる

    Args:
        pid: プロセスID
        timeout: タイムアウト秒数

    Returns:
        bool: 正常に終了した場合True
    """
    if not is_process_running(pid):
        return True

    try:
        # まずSIGTERMを送信
        os.kill(pid, signal.SIGTERM)

        # タイムアウトまで待機
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not is_process_running(pid):
                return True
            time.sleep(0.1)

        # まだ実行中の場合はSIGKILLを送信
        logger.warning(f"プロセス {pid} がSIGTERMで終了しないため、SIGKILLを送信します")
        os.kill(pid, signal.SIGKILL)

        # 再度確認
        time.sleep(0.5)
        return not is_process_running(pid)

    except OSError as e:
        logger.error(f"プロセス {pid} の終了に失敗しました: {e}")
        return False


def ensure_directory(path: Path) -> None:
    """ディレクトリが存在しない場合は作成

    Args:
        path: ディレクトリパス
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"ディレクトリの作成に失敗しました: {path} - {e}")
        raise


def safe_write_file(file_path: Path, content: str, encoding: str = "utf-8") -> bool:
    """ファイルを安全に書き込み

    Args:
        file_path: ファイルパス
        content: 書き込み内容
        encoding: エンコーディング

    Returns:
        bool: 成功した場合True
    """
    try:
        ensure_directory(file_path.parent)

        # 一時ファイルに書き込んでから移動（アトミック操作）
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)

        temp_path.replace(file_path)
        return True

    except Exception as e:
        logger.error(f"ファイルの書き込みに失敗しました: {file_path} - {e}")
        return False


def safe_read_file(file_path: Path, encoding: str = "utf-8") -> Optional[str]:
    """ファイルを安全に読み込み

    Args:
        file_path: ファイルパス
        encoding: エンコーディング

    Returns:
        Optional[str]: ファイル内容（失敗時はNone）
    """
    try:
        if not file_path.exists():
            return None

        with open(file_path, encoding=encoding) as f:
            return f.read()

    except Exception as e:
        logger.error(f"ファイルの読み込みに失敗しました: {file_path} - {e}")
        return None


class AsyncTimer:
    """非同期タイマークラス"""

    def __init__(self, interval: float, callback: Callable[[], Awaitable[None]]):
        self.interval = interval
        self.callback = callback
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """タイマーを開始"""
        if self._task is not None:
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """タイマーを停止"""
        if self._task is None:
            return

        self._stop_event.set()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None

    async def _run(self) -> None:
        """タイマーのメインループ"""
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval)
                    break  # 停止イベントが設定された
                except asyncio.TimeoutError:
                    # タイムアウト = 通常の実行
                    try:
                        await self.callback()
                    except Exception as e:
                        logger.error(f"タイマーコールバックでエラーが発生しました: {e}")
        except asyncio.CancelledError:
            logger.debug("タイマータスクがキャンセルされました")
            raise


@asynccontextmanager
async def async_timeout(seconds: float):
    """非同期タイムアウトコンテキストマネージャー

    Args:
        seconds: タイムアウト秒数
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError:
        logger.warning(f"操作がタイムアウトしました: {seconds}秒")
        raise


def format_bytes(bytes_count: int) -> str:
    """バイト数を人間が読みやすい形式にフォーマット

    Args:
        bytes_count: バイト数

    Returns:
        str: フォーマットされた文字列
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """文字列を指定された長さで切り詰める

    Args:
        text: 対象文字列
        max_length: 最大長
        suffix: 切り詰め時の接尾辞

    Returns:
        str: 切り詰められた文字列
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """ファイル名を安全な形式にサニタイズ

    Args:
        filename: 元のファイル名

    Returns:
        str: サニタイズされたファイル名
    """
    # 危険な文字を置換
    dangerous_chars = '<>:"/\\|?*'
    for char in dangerous_chars:
        filename = filename.replace(char, "_")

    # 先頭・末尾の空白とピリオドを削除
    filename = filename.strip(" .")

    # 空文字列の場合はデフォルト名を使用
    if not filename:
        filename = "unnamed"

    return filename


class DebugTimer:
    """デバッグ用のタイマークラス"""

    def __init__(self, name: str):
        self.name = name
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        logger.debug(f"[{self.name}] 開始")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            logger.debug(f"[{self.name}] 完了 ({elapsed:.3f}秒)")


def get_env_bool(key: str, default: bool = False) -> bool:
    """環境変数をbool値として取得

    Args:
        key: 環境変数名
        default: デフォルト値

    Returns:
        bool: 環境変数の値
    """
    value = os.getenv(key)
    if value is None:
        return default

    return value.lower() in ("true", "1", "yes", "on")


def get_env_int(key: str, default: int = 0) -> int:
    """環境変数をint値として取得

    Args:
        key: 環境変数名
        default: デフォルト値

    Returns:
        int: 環境変数の値
    """
    value = os.getenv(key)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        logger.warning(f"環境変数 {key} の値が不正です: {value}")
        return default
