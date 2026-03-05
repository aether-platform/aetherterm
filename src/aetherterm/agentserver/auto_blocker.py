"""
自動ブロック機能
危険検出時にクライアントに入力ブロック指示を送信する
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

log = logging.getLogger("aetherterm.auto_blocker")


class BlockReason(Enum):
    """ブロック理由"""

    CRITICAL_KEYWORD = "critical_keyword"
    MULTIPLE_WARNINGS = "multiple_warnings"
    MANUAL_BLOCK = "manual_block"
    SYSTEM_PROTECTION = "system_protection"


@dataclass
class BlockState:
    """ブロック状態"""

    session_id: str
    is_blocked: bool
    reason: BlockReason
    message: str
    alert_message: str
    detected_keywords: list
    blocked_at: float
    unlock_key: str = "ctrl_d"


class AutoBlocker:
    """自動ブロック管理クラス"""

    def __init__(self, socket_io_instance=None):
        self.sio = socket_io_instance
        self.blocked_sessions: dict[str, BlockState] = {}

    def set_socket_io(self, sio_instance):
        """Socket.IOインスタンスを設定"""
        self.sio = sio_instance

    def block_session(
        self,
        session_id: str,
        reason: BlockReason,
        message: str,
        alert_message: str,
        detected_keywords: Optional[list] = None,
    ) -> bool:
        """
        セッションをブロック

        Args:
            session_id: セッションID
            reason: ブロック理由
            message: ブロックメッセージ
            alert_message: 警告メッセージ
            detected_keywords: 検出されたキーワード

        Returns:
            bool: ブロック成功フラグ
        """
        if not self.sio:
            log.error("Socket.IO instance not set")
            return False

        block_state = BlockState(
            session_id=session_id,
            is_blocked=True,
            reason=reason,
            message=message,
            alert_message=alert_message,
            detected_keywords=detected_keywords or [],
            blocked_at=time.time(),
        )

        self.blocked_sessions[session_id] = block_state

        # クライアントにブロック指示を送信
        block_data = {
            "type": "auto_block",
            "session_id": session_id,
            "severity": self._get_severity_from_reason(reason),
            "message": message,
            "detected_keywords": detected_keywords or [],
            "alert_message": alert_message,
            "unlock_key": block_state.unlock_key,
            "timestamp": block_state.blocked_at,
        }

        try:
            # 特定のセッションに接続されているクライアントに送信
            import asyncio

            _ = asyncio.create_task(self.sio.emit("auto_block", block_data))

            log.info(f"Session {session_id} blocked: {reason.value} - {message}")
            return True

        except Exception as e:
            log.error(f"Failed to send block signal to session {session_id}: {e}")
            return False

    def unblock_session(self, session_id: str, unlock_key: str = "ctrl_d") -> bool:
        """
        セッションのブロックを解除

        Args:
            session_id: セッションID
            unlock_key: 解除キー

        Returns:
            bool: 解除成功フラグ
        """
        if session_id not in self.blocked_sessions:
            log.warning(f"Session {session_id} is not blocked")
            return False

        block_state = self.blocked_sessions[session_id]

        # 解除キーの確認
        if unlock_key != block_state.unlock_key:
            log.warning(f"Invalid unlock key for session {session_id}: {unlock_key}")
            return False

        # ブロック状態を削除
        del self.blocked_sessions[session_id]

        # クライアントにブロック解除を通知
        unblock_data = {
            "type": "auto_unblock",
            "session_id": session_id,
            "message": "ブロックが解除されました",
            "timestamp": time.time(),
        }

        try:
            import asyncio

            _ = asyncio.create_task(self.sio.emit("auto_unblock", unblock_data))

            log.info(f"Session {session_id} unblocked")
            return True

        except Exception as e:
            log.error(f"Failed to send unblock signal to session {session_id}: {e}")
            return False

    def is_session_blocked(self, session_id: str) -> bool:
        """セッションがブロックされているかチェック"""
        return session_id in self.blocked_sessions

    def get_block_state(self, session_id: str) -> Optional[BlockState]:
        """セッションのブロック状態を取得"""
        return self.blocked_sessions.get(session_id)

    def get_all_blocked_sessions(self) -> dict[str, BlockState]:
        """すべてのブロックされたセッションを取得"""
        return self.blocked_sessions.copy()

    def force_unblock_session(self, session_id: str) -> bool:
        """強制的にセッションのブロックを解除(管理者用)"""
        if session_id in self.blocked_sessions:
            del self.blocked_sessions[session_id]

            # クライアントに強制解除を通知
            force_unblock_data = {
                "type": "force_unblock",
                "session_id": session_id,
                "message": "管理者によってブロックが強制解除されました",
                "timestamp": time.time(),
            }

            try:
                import asyncio

                _ = asyncio.create_task(self.sio.emit("force_unblock", force_unblock_data))

                log.info(f"Session {session_id} force unblocked by admin")
                return True

            except Exception as e:
                log.error(f"Failed to send force unblock signal to session {session_id}: {e}")
                return False

        return False

    def cleanup_expired_blocks(self, max_age_seconds: int = 300):
        """期限切れのブロックをクリーンアップ(5分でタイムアウト)"""
        current_time = time.time()
        expired_sessions = []

        for session_id, block_state in self.blocked_sessions.items():
            if current_time - block_state.blocked_at > max_age_seconds:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            log.info(f"Auto-unblocking expired session: {session_id}")
            self.force_unblock_session(session_id)

    def _get_severity_from_reason(self, reason: BlockReason) -> str:
        """ブロック理由から危険度を取得"""
        severity_map = {
            BlockReason.CRITICAL_KEYWORD: "critical",
            BlockReason.MULTIPLE_WARNINGS: "high",
            BlockReason.MANUAL_BLOCK: "medium",
            BlockReason.SYSTEM_PROTECTION: "critical",
        }
        return severity_map.get(reason, "medium")

    def get_statistics(self) -> dict:
        """ブロック統計を取得"""
        if not self.blocked_sessions:
            return {"total_blocked": 0, "by_reason": {}, "oldest_block": None, "newest_block": None}

        by_reason = {}
        timestamps = []

        for block_state in self.blocked_sessions.values():
            reason_key = block_state.reason.value
            by_reason[reason_key] = by_reason.get(reason_key, 0) + 1
            timestamps.append(block_state.blocked_at)

        return {
            "total_blocked": len(self.blocked_sessions),
            "by_reason": by_reason,
            "oldest_block": min(timestamps) if timestamps else None,
            "newest_block": max(timestamps) if timestamps else None,
        }


# --- レガシーグローバル状態 (非推奨) ---
# 新規コードでは ApplicationContainer.blocker_use_cases を使用してください。
# domain/services/session_blocker.py + application/use_cases/blocker_use_cases.py が後継です。

import warnings as _warnings

_auto_blocker_instance = None


def get_auto_blocker() -> AutoBlocker:
    """自動ブロッカーのシングルトンインスタンスを取得

    .. deprecated::
        ApplicationContainer.blocker_use_cases を使用してください。
    """
    _warnings.warn(
        "get_auto_blocker() is deprecated. Use ApplicationContainer.blocker_use_cases instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    global _auto_blocker_instance
    if _auto_blocker_instance is None:
        _auto_blocker_instance = AutoBlocker()
    return _auto_blocker_instance


def set_socket_io_instance(sio_instance):
    """Socket.IOインスタンスをグローバルブロッカーに設定

    .. deprecated::
        ApplicationContainer.broadcaster を使用してください。
    """
    _warnings.warn(
        "set_socket_io_instance() is deprecated. Use ApplicationContainer.broadcaster instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    blocker = get_auto_blocker()
    blocker.set_socket_io(sio_instance)
