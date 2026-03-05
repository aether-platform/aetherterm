"""コマンドインターセプター

PTYモニターと連携して、リアルタイムでコマンドを解析し、
危険なコマンドの実行を防ぎます。
"""

import logging
from typing import Any, Callable, Dict, Optional

from ...common.agent_protocol import (
    InterventionData,
    InterventionType,
)
from ..agents import AgentManager, CommandAnalyzerAgent

logger = logging.getLogger(__name__)


class CommandInterceptor:
    """コマンドインターセプター

    PTYの入出力を監視し、CommandAnalyzerAgentと連携して
    リアルタイムでコマンドを解析します。
    """

    def __init__(
        self, agent_manager: Optional[AgentManager] = None, auto_block_dangerous: bool = True
    ):
        """初期化

        Args:
            agent_manager: エージェントマネージャー
            auto_block_dangerous: 危険なコマンドを自動的にブロックするか
        """
        self.agent_manager = agent_manager or AgentManager()
        self.auto_block_dangerous = auto_block_dangerous

        # CommandAnalyzerAgentのID
        self.analyzer_agent_id = "command_analyzer_001"
        self.analyzer_agent: Optional[CommandAnalyzerAgent] = None

        # コマンドバッファ（複数行コマンド対応）
        self.command_buffer = ""
        self.in_multiline = False

        # コールバック
        self.on_command_analyzed: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_command_blocked: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_user_approval: Optional[Callable[[str], bool]] = None

        # 統計
        self.stats = {
            "total_commands": 0,
            "blocked_commands": 0,
            "approved_commands": 0,
            "safe_commands": 0,
        }

    async def initialize(self) -> bool:
        """初期化"""
        try:
            logger.info("コマンドインターセプターを初期化中...")

            # CommandAnalyzerAgentを作成
            self.analyzer_agent = CommandAnalyzerAgent(self.analyzer_agent_id)

            # 介入コールバックを設定
            self.analyzer_agent.set_intervention_callback(self._handle_intervention)

            # エージェントを登録
            self.agent_manager.register_agent(self.analyzer_agent)

            # エージェントを開始
            success = await self.agent_manager.start_agent(self.analyzer_agent_id)

            if success:
                logger.info("コマンドインターセプターの初期化が完了しました")
            else:
                logger.error("CommandAnalyzerAgentの開始に失敗しました")

            return success

        except Exception as e:
            logger.error(f"コマンドインターセプターの初期化に失敗しました: {e}")
            return False

    async def shutdown(self) -> None:
        """シャットダウン"""
        logger.info("コマンドインターセプターをシャットダウン中...")

        if self.analyzer_agent_id:
            await self.agent_manager.stop_agent(self.analyzer_agent_id)

        logger.info("コマンドインターセプターのシャットダウンが完了しました")

    async def intercept_input(self, data: bytes) -> Optional[bytes]:
        """入力をインターセプト

        Args:
            data: PTYへの入力データ

        Returns:
            Optional[bytes]: 処理後のデータ（Noneの場合はブロック）
        """
        try:
            # バイトを文字列に変換
            text = data.decode("utf-8", errors="ignore")

            # コマンドバッファに追加
            self.command_buffer += text

            # 改行が含まれている場合はコマンドとして処理
            if "\n" in text or "\r" in text:
                command = self.command_buffer.strip()
                self.command_buffer = ""

                if command:
                    # コマンドを解析
                    result = await self._analyze_command(command)

                    # ブロック判定
                    if self._should_block_command(result):
                        logger.warning(f"危険なコマンドをブロックしました: {command}")
                        self.stats["blocked_commands"] += 1

                        if self.on_command_blocked:
                            self.on_command_blocked(command, result)

                        # ブロックメッセージを返す
                        block_msg = (
                            "\r\n[BLOCKED] このコマンドは安全性の問題によりブロックされました。\r\n"
                        )
                        return block_msg.encode("utf-8")

                    self.stats["safe_commands"] += 1

            return data

        except Exception as e:
            logger.error(f"入力インターセプト中にエラーが発生しました: {e}")
            return data

    async def intercept_output(self, data: bytes) -> bytes:
        """出力をインターセプト（現在は通過のみ）

        Args:
            data: PTYからの出力データ

        Returns:
            bytes: 処理後のデータ
        """
        return data

    async def _analyze_command(self, command: str) -> Dict[str, Any]:
        """コマンドを解析"""
        self.stats["total_commands"] += 1

        if not self.analyzer_agent:
            logger.error("CommandAnalyzerAgentが初期化されていません")
            return {"command": command, "safety": {"is_safe": True, "risk_level": "unknown"}}

        try:
            # 直接解析メソッドを呼び出し（高速化のため）
            result = await self.analyzer_agent.analyze_command_stream(command)

            # コールバック通知
            if self.on_command_analyzed:
                self.on_command_analyzed(result)

            return result

        except Exception as e:
            logger.error(f"コマンド解析中にエラーが発生しました: {e}")
            return {"command": command, "safety": {"is_safe": True, "risk_level": "error"}}

    def _should_block_command(self, analysis_result: Dict[str, Any]) -> bool:
        """コマンドをブロックすべきか判定"""
        if not self.auto_block_dangerous:
            return False

        safety = analysis_result.get("safety", {})
        risk_level = safety.get("risk_level", "safe")

        # CRITICALレベルは常にブロック
        if risk_level == "critical":
            return True

        # ユーザー承認が拒否された場合
        if "user_approval" in analysis_result and not analysis_result["user_approval"]:
            return True

        return False

    async def _handle_intervention(self, intervention: InterventionData) -> Any:
        """介入要求を処理"""
        if intervention.type == InterventionType.APPROVAL:
            # ユーザー承認が必要
            if self.on_user_approval:
                command = intervention.context.get("command", "")
                approved = self.on_user_approval(command)

                if approved:
                    self.stats["approved_commands"] += 1

                return "approved" if approved else "rejected"
            # コールバックが設定されていない場合は自動承認（デフォルト安全）
            return "approved"

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        stats = self.stats.copy()

        # 安全率を計算
        if stats["total_commands"] > 0:
            stats["safety_rate"] = stats["safe_commands"] / stats["total_commands"]
            stats["block_rate"] = stats["blocked_commands"] / stats["total_commands"]
        else:
            stats["safety_rate"] = 1.0
            stats["block_rate"] = 0.0

        # エージェントの統計も含める
        if self.analyzer_agent:
            session_stats = self.analyzer_agent._get_session_stats()
            stats["session_stats"] = session_stats

        return stats

    def reset_statistics(self) -> None:
        """統計をリセット"""
        self.stats = {
            "total_commands": 0,
            "blocked_commands": 0,
            "approved_commands": 0,
            "safe_commands": 0,
        }
