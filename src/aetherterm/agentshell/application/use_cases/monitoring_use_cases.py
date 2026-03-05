"""
監視関連ユースケース

ターミナル出力の脅威検出と入力ブロックのビジネスフローを定義します。
"""

import logging
from typing import Optional

from ...domain.services.command_threat_analyzer import CommandThreatAnalyzer, ThreatAnalysisResult
from ...domain.services.input_policy import BlockState, InputPolicyService
from ..ports.ai_provider import AIProviderPort
from ..ports.server_connector import ServerConnectorPort
from ..ports.terminal_io import TerminalIOPort

logger = logging.getLogger(__name__)


class MonitoringUseCases:
    """ターミナル監視ユースケース"""

    def __init__(
        self,
        threat_analyzer: CommandThreatAnalyzer,
        input_policy: InputPolicyService,
        terminal_io: TerminalIOPort,
        ai_provider: Optional[AIProviderPort] = None,
        server_connector: Optional[ServerConnectorPort] = None,
    ):
        self._threat_analyzer = threat_analyzer
        self._input_policy = input_policy
        self._terminal_io = terminal_io
        self._ai_provider = ai_provider
        self._server_connector = server_connector

    async def analyze_output(self, session_id: str, output: str) -> Optional[ThreatAnalysisResult]:
        """
        ターミナル出力を解析し、脅威を検出して必要に応じてブロック

        Returns:
            ThreatAnalysisResult if threat detected, None otherwise
        """
        result = self._threat_analyzer.analyze(output)

        if result.should_block:
            self._input_policy.block(result.message)
            await self._terminal_io.send_warning(
                f"Dangerous activity detected: {result.message}\n"
                "Press Ctrl+D twice to unblock."
            )

            # サーバーに通知
            if self._server_connector and await self._server_connector.is_connected():
                await self._server_connector.send_event(
                    "threat_detected",
                    {
                        "session_id": session_id,
                        "threat_level": result.threat_level.value,
                        "detected_keywords": result.detected_keywords,
                        "message": result.message,
                    },
                )

            logger.warning(f"Session {session_id} blocked: {result.message}")

        return result if result.detected_keywords else None

    async def handle_ctrl_d(self, session_id: str) -> BlockState:
        """Ctrl+D入力を処理"""
        new_state = self._input_policy.handle_ctrl_d()

        if new_state == BlockState.WAITING_CONFIRMATION:
            await self._terminal_io.send_warning(
                "Press Ctrl+D again to confirm unblock."
            )
        elif new_state == BlockState.NORMAL:
            await self._terminal_io.send_warning("Input unblocked.")

        return new_state

    def is_input_blocked(self) -> bool:
        return self._input_policy.is_blocked

    async def analyze_command_with_ai(
        self, command: str, context: Optional[str] = None
    ) -> Optional[dict]:
        """AIを使用してコマンドを分析"""
        if self._ai_provider and await self._ai_provider.is_available():
            return await self._ai_provider.analyze_command(command, context)
        return None
