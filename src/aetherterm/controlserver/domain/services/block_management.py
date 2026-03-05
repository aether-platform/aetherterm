"""
ブロック管理ドメインサービス

セッションブロックのビジネスルールを管理する
純粋なロジック（NATS等のインフラに依存しません）。
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ..entities import BlockCommand

logger = logging.getLogger(__name__)


class BlockManagementService:
    """ブロック管理サービス（ドメインサービス）"""

    def __init__(self):
        self.active_blocks: Dict[str, BlockCommand] = {}
        self.block_history: List[BlockCommand] = []

    def create_block(
        self,
        block_type: str,
        reason: str,
        affected_sessions: List[str],
        admin_user: Optional[str] = None,
    ) -> BlockCommand:
        """ブロックコマンドを作成し記録"""
        block_id = str(uuid.uuid4())
        block_command = BlockCommand(
            block_id=block_id,
            block_type=block_type,
            reason=reason,
            admin_user=admin_user,
            affected_sessions=affected_sessions,
            timestamp=datetime.now().isoformat(),
        )

        self.active_blocks[block_id] = block_command
        self.block_history.append(block_command)
        logger.info(f"Block created: {block_id} ({block_type}): {reason}")
        return block_command

    def remove_block_for_session(self, session_id: str) -> Optional[str]:
        """セッションのブロックを解除し、block_idを返す"""
        block_to_remove = None
        for block_id, block_cmd in self.active_blocks.items():
            if session_id in block_cmd.affected_sessions:
                block_to_remove = block_id
                break

        if block_to_remove:
            del self.active_blocks[block_to_remove]
            return block_to_remove
        return None

    def get_active_blocks(self) -> Dict[str, BlockCommand]:
        return self.active_blocks.copy()

    def get_block_history(self, limit: int = 50) -> List[BlockCommand]:
        return self.block_history[-limit:]
