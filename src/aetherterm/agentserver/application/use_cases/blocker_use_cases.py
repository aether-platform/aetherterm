"""
ブロッカー関連ユースケース

セッションのブロック/アンブロックのビジネスフローを定義します。
"""

import logging
import time
from typing import Dict, Optional

from ...domain.entities import BlockReason, BlockState
from ...domain.services.session_blocker import SessionBlockerService
from ..ports.broadcaster import BroadcasterPort
from ..ports.terminal_repository import TerminalRepositoryPort

logger = logging.getLogger(__name__)


class BlockerUseCases:
    """ブロッカー関連ユースケース"""

    def __init__(
        self,
        session_blocker: SessionBlockerService,
        broadcaster: BroadcasterPort,
        terminal_repo: TerminalRepositoryPort,
    ):
        self._session_blocker = session_blocker
        self._broadcaster = broadcaster
        self._terminal_repo = terminal_repo

    async def unblock_session(self, session_id: str, unlock_key: str = "ctrl_d") -> bool:
        """セッションのブロックを解除し、クライアントに通知"""
        success = self._session_blocker.unblock_session(session_id, unlock_key)

        if success:
            client_sids = list(self._terminal_repo.get_client_sids(session_id))
            await self._broadcaster.emit_to_clients(
                "auto_unblock",
                {
                    "type": "auto_unblock",
                    "session_id": session_id,
                    "message": "ブロックが解除されました",
                    "timestamp": time.time(),
                },
                client_sids,
            )

        return success

    async def force_unblock_session(self, session_id: str) -> bool:
        """管理者による強制ブロック解除"""
        success = self._session_blocker.force_unblock_session(session_id)

        if success:
            client_sids = list(self._terminal_repo.get_client_sids(session_id))
            await self._broadcaster.emit_to_clients(
                "force_unblock",
                {
                    "type": "force_unblock",
                    "session_id": session_id,
                    "message": "管理者によってブロックが強制解除されました",
                    "timestamp": time.time(),
                },
                client_sids,
            )

        return success

    def is_session_blocked(self, session_id: str) -> bool:
        return self._session_blocker.is_session_blocked(session_id)

    def get_block_state(self, session_id: str) -> Optional[BlockState]:
        return self._session_blocker.get_block_state(session_id)

    def get_statistics(self) -> dict:
        return self._session_blocker.get_statistics()

    async def cleanup_expired_blocks(self, max_age_seconds: int = 300) -> None:
        """期限切れブロックをクリーンアップし、クライアントに通知"""
        expired_sids = self._session_blocker.cleanup_expired_blocks(max_age_seconds)

        for sid in expired_sids:
            client_sids = list(self._terminal_repo.get_client_sids(sid))
            await self._broadcaster.emit_to_clients(
                "force_unblock",
                {
                    "type": "force_unblock",
                    "session_id": sid,
                    "message": "タイムアウトによりブロックが自動解除されました",
                    "timestamp": time.time(),
                },
                client_sids,
            )
