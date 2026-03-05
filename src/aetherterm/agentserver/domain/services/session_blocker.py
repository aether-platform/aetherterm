"""
セッションブロッカードメインサービス

セッションのブロック/アンブロック状態を管理する
純粋なビジネスロジック（フレームワーク非依存）。
通知の送信は OutputPort 経由で外部に委譲します。
"""

import logging
import time
from typing import Callable, Dict, Optional

from ..entities import BlockReason, BlockState

logger = logging.getLogger(__name__)


class SessionBlockerService:
    """セッションブロック管理サービス（ドメインサービス）"""

    def __init__(self):
        self._blocked_sessions: Dict[str, BlockState] = {}

    def block_session(
        self,
        session_id: str,
        reason: BlockReason,
        message: str,
        alert_message: str,
        detected_keywords: Optional[list] = None,
    ) -> Optional[BlockState]:
        """
        セッションをブロック

        Returns:
            BlockState if blocked successfully, None if already blocked
        """
        block_state = BlockState(
            session_id=session_id,
            is_blocked=True,
            reason=reason,
            message=message,
            alert_message=alert_message,
            detected_keywords=detected_keywords or [],
        )

        self._blocked_sessions[session_id] = block_state
        logger.info(f"Session {session_id} blocked: {reason.value} - {message}")
        return block_state

    def unblock_session(self, session_id: str, unlock_key: str = "ctrl_d") -> bool:
        """セッションのブロックを解除"""
        if session_id not in self._blocked_sessions:
            return False

        block_state = self._blocked_sessions[session_id]
        if unlock_key != block_state.unlock_key:
            logger.warning(f"Invalid unlock key for session {session_id}")
            return False

        del self._blocked_sessions[session_id]
        logger.info(f"Session {session_id} unblocked")
        return True

    def force_unblock_session(self, session_id: str) -> bool:
        """強制的にセッションのブロックを解除"""
        if session_id not in self._blocked_sessions:
            return False

        del self._blocked_sessions[session_id]
        logger.info(f"Session {session_id} force unblocked")
        return True

    def is_session_blocked(self, session_id: str) -> bool:
        return session_id in self._blocked_sessions

    def get_block_state(self, session_id: str) -> Optional[BlockState]:
        return self._blocked_sessions.get(session_id)

    def get_all_blocked_sessions(self) -> Dict[str, BlockState]:
        return self._blocked_sessions.copy()

    def cleanup_expired_blocks(self, max_age_seconds: int = 300) -> list[str]:
        """期限切れブロックをクリーンアップし、解除されたセッションIDリストを返す"""
        current_time = time.time()
        expired = [
            sid
            for sid, state in self._blocked_sessions.items()
            if current_time - state.blocked_at > max_age_seconds
        ]

        for sid in expired:
            del self._blocked_sessions[sid]
            logger.info(f"Auto-unblocking expired session: {sid}")

        return expired

    def get_statistics(self) -> dict:
        if not self._blocked_sessions:
            return {"total_blocked": 0, "by_reason": {}, "oldest_block": None, "newest_block": None}

        by_reason: Dict[str, int] = {}
        timestamps = []

        for state in self._blocked_sessions.values():
            key = state.reason.value
            by_reason[key] = by_reason.get(key, 0) + 1
            timestamps.append(state.blocked_at)

        return {
            "total_blocked": len(self._blocked_sessions),
            "by_reason": by_reason,
            "oldest_block": min(timestamps),
            "newest_block": max(timestamps),
        }
