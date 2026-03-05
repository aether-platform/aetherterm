"""
入力ポリシードメインサービス

ブロック状態の管理とアンブロック条件の判定を行う
純粋なビジネスロジック（フレームワーク非依存）。
ターミナルI/O操作はポートに委譲します。
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class BlockState(str, Enum):
    """ブロック状態"""

    NORMAL = "normal"
    BLOCKED = "blocked"
    WAITING_CONFIRMATION = "waiting_confirmation"


class InputPolicyService:
    """入力ポリシーサービス（ドメインサービス）"""

    def __init__(self):
        self._state: BlockState = BlockState.NORMAL
        self._block_reason: Optional[str] = None

    @property
    def state(self) -> BlockState:
        return self._state

    @property
    def is_blocked(self) -> bool:
        return self._state != BlockState.NORMAL

    @property
    def block_reason(self) -> Optional[str]:
        return self._block_reason

    def block(self, reason: str) -> None:
        """入力をブロック"""
        self._state = BlockState.BLOCKED
        self._block_reason = reason
        logger.warning(f"Input blocked: {reason}")

    def request_confirmation(self) -> bool:
        """確認待ち状態に遷移（Ctrl+D 1回目）"""
        if self._state == BlockState.BLOCKED:
            self._state = BlockState.WAITING_CONFIRMATION
            return True
        return False

    def confirm_unblock(self) -> bool:
        """ブロック解除を確認（Ctrl+D 2回目）"""
        if self._state == BlockState.WAITING_CONFIRMATION:
            self._state = BlockState.NORMAL
            self._block_reason = None
            logger.info("Input unblocked by user confirmation")
            return True
        return False

    def force_unblock(self) -> None:
        """強制的にブロック解除"""
        self._state = BlockState.NORMAL
        self._block_reason = None
        logger.info("Input force unblocked")

    def handle_ctrl_d(self) -> BlockState:
        """Ctrl+D入力を処理し、新しい状態を返す"""
        if self._state == BlockState.BLOCKED:
            self.request_confirmation()
            return BlockState.WAITING_CONFIRMATION
        elif self._state == BlockState.WAITING_CONFIRMATION:
            self.confirm_unblock()
            return BlockState.NORMAL
        return self._state
