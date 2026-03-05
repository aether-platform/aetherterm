"""
ターミナル関連ユースケース

ターミナルセッションの作成、入出力処理、ブロードキャストの
ビジネスフローを定義します。
"""

import logging
from typing import Optional

from ...domain.entities import BlockReason, SeverityLevel, UserInfo, check_session_ownership
from ...domain.services.session_blocker import SessionBlockerService
from ...domain.services.threat_detection import ThreatDetectionService
from ..ports.broadcaster import BroadcasterPort
from ..ports.terminal_repository import TerminalRepositoryPort

logger = logging.getLogger(__name__)


class TerminalUseCases:
    """ターミナル関連ユースケース"""

    def __init__(
        self,
        terminal_repo: TerminalRepositoryPort,
        broadcaster: BroadcasterPort,
        threat_detector: ThreatDetectionService,
        session_blocker: SessionBlockerService,
    ):
        self._terminal_repo = terminal_repo
        self._broadcaster = broadcaster
        self._threat_detector = threat_detector
        self._session_blocker = session_blocker

    async def broadcast_terminal_output(
        self,
        session_id: str,
        message: Optional[str],
    ) -> None:
        """
        ターミナル出力をクライアントにブロードキャスト

        脅威検出を実行し、必要に応じて自動ブロックを適用します。
        """
        client_sids = self._terminal_repo.get_client_sids(session_id)
        client_sid_list = list(client_sids)

        if message is not None:
            # リアルタイム脅威検出
            detection = self._threat_detector.analyze_output(session_id, message)

            if detection and detection.should_block:
                reason = (
                    BlockReason.CRITICAL_KEYWORD
                    if detection.severity == SeverityLevel.CRITICAL
                    else BlockReason.MULTIPLE_WARNINGS
                )

                block_state = self._session_blocker.block_session(
                    session_id=session_id,
                    reason=reason,
                    message=detection.message,
                    alert_message=detection.alert_message,
                    detected_keywords=detection.detected_keywords,
                )

                if block_state:
                    logger.warning(
                        f"Session {session_id} automatically blocked: {detection.message}"
                    )
                    await self._broadcaster.emit_to_clients(
                        "auto_block", block_state.to_dict(), client_sid_list
                    )

            # ターミナル出力をブロードキャスト
            await self._broadcaster.emit_to_clients(
                "terminal_output",
                {"session": session_id, "data": message},
                client_sid_list,
            )
        else:
            # ターミナルが閉じられた
            await self._broadcaster.emit_to_clients(
                "terminal_closed",
                {"session": session_id},
                client_sid_list,
            )

    def check_session_ownership(
        self, session_id: str, user_info: UserInfo
    ) -> bool:
        """セッション所有権を確認"""
        owner = self._terminal_repo.get_session_owner(session_id)
        return check_session_ownership(owner, user_info)

    def get_terminal_context(self, session_id: str) -> Optional[str]:
        """AI支援用のターミナルコンテキストを取得"""
        return self._terminal_repo.get_terminal_context(session_id)
