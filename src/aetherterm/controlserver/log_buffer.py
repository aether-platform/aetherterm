"""LogBuffer - セッション単位のハイブリッドバッファ

件数ベース + 時間ベースのハイブリッドフラッシュでログを蓄積し、
閾値到達時にコールバックを呼び出す。
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .log_analysis_config import LogAnalysisConfig

logger = logging.getLogger(__name__)


@dataclass
class SessionLogBuffer:
    """1セッション分のバッファ"""

    lines: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_flush: float = field(default_factory=time.time)


class LogBufferManager:
    """全セッションのバッファを管理"""

    def __init__(
        self,
        config: LogAnalysisConfig,
        on_flush: Callable[[str, list[dict]], Awaitable[None]],
    ):
        self._config = config
        self._on_flush = on_flush
        self._buffers: dict[str, SessionLogBuffer] = {}
        self._timer_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def add(self, session_id: str, entries: list[dict]) -> None:
        """ログエントリをバッファに追加

        件数閾値に達した場合は即時フラッシュ。
        """
        async with self._lock:
            if session_id not in self._buffers:
                self._buffers[session_id] = SessionLogBuffer()

            buf = self._buffers[session_id]
            buf.lines.extend(entries)

            # 件数閾値チェック
            if len(buf.lines) >= self._config.buffer_max_lines:
                await self._flush_session(session_id)

    async def start_timer(self) -> None:
        """定期フラッシュタイマー開始"""
        if self._timer_task is None:
            self._timer_task = asyncio.create_task(self._timer_loop())
            logger.info("LogBufferManager timer started")

    async def stop(self) -> None:
        """タイマー停止 + 残存バッファをフラッシュ"""
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None

        # 残存バッファをフラッシュ
        async with self._lock:
            for session_id in list(self._buffers.keys()):
                if self._buffers[session_id].lines:
                    await self._flush_session(session_id)

        logger.info("LogBufferManager stopped")

    async def _timer_loop(self) -> None:
        """定期的に時間ベースのフラッシュをチェック"""
        check_interval = max(self._config.buffer_max_interval_sec // 4, 5)
        while True:
            await asyncio.sleep(check_interval)
            async with self._lock:
                now = time.time()
                for session_id in list(self._buffers.keys()):
                    buf = self._buffers[session_id]
                    elapsed = now - buf.last_flush
                    has_enough = len(buf.lines) >= self._config.buffer_min_lines
                    if elapsed >= self._config.buffer_max_interval_sec and has_enough:
                        await self._flush_session(session_id)

    async def _flush_session(self, session_id: str) -> None:
        """セッションのバッファをフラッシュ（ロック取得済み前提）"""
        buf = self._buffers.get(session_id)
        if not buf or not buf.lines:
            return

        entries = buf.lines
        buf.lines = []
        buf.last_flush = time.time()

        logger.debug(f"Flushing {len(entries)} log entries for session {session_id}")

        try:
            await self._on_flush(session_id, entries)
        except Exception:
            logger.exception(f"Error in on_flush callback for session {session_id}")

    def get_buffer_stats(self) -> dict:
        """バッファ統計を取得"""
        return {
            session_id: {
                "buffered_lines": len(buf.lines),
                "created_at": buf.created_at,
                "last_flush": buf.last_flush,
            }
            for session_id, buf in self._buffers.items()
        }
