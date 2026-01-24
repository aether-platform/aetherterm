"""
リアルタイムコンテキスト推定エンジン

現在のコマンド履歴から実行中のオペレーションを推定し、
次のアクションを予測する。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from aetherterm.langchain.storage.sql_adapter import SQLStorageAdapter
from aetherterm.langchain.storage.vector_adapter import VectorStorageAdapter

from .models import (
    ContextInferenceResult,
    OperationContext,
    OperationStage,
    OperationType,
)
from .pattern_learner import OperationPatternLearner

logger = logging.getLogger(__name__)
class OperationContextInferenceEngine:
    """オペレーションコンテキスト推定エンジン"""

    def __init__(
        self,
        vector_storage: VectorStorageAdapter,
        sql_storage: SQLStorageAdapter,
        pattern_learner: OperationPatternLearner,
    ):
        self.vector_storage = vector_storage
        self.sql_storage = sql_storage
        self.pattern_learner = pattern_learner
        self.logger = logger

        # 推定設定
        self.recent_commands_window = 10  # 最近のコマンド数
        self.context_timeout = 3600  # コンテキストタイムアウト（秒）
        self.min_confidence_threshold = 0.6

        # 現在のコンテキスト追跡
        self.active_contexts: Dict[str, OperationContext] = {}
        self.context_history: Dict[str, List[OperationContext]] = {}

    async def infer_current_operation(self, terminal_id: str) -> ContextInferenceResult:
        """
        現在のオペレーションを推定

        Args:
            terminal_id: ターミナルID

        Returns:
            推定結果
        """
        try:
            self.logger.debug(f"Inferring operation context for terminal {terminal_id}")

            # 最近のコマンド履歴を取得
            recent_commands = await self._get_recent_commands(terminal_id)

            if not recent_commands:
                return self._create_empty_result(terminal_id)

            # 既存のコンテキストを確認
            existing_context = await self._check_existing_context(terminal_id, recent_commands)

            if existing_context:
                # 既存コンテキストを更新
                updated_context = await self._update_existing_context(
                    existing_context, recent_commands
                )
                return self._create_result_from_context(terminal_id, updated_context)

            # 新しいコンテキストを推定
            new_context = await self._infer_new_context(terminal_id, recent_commands)

            if new_context and new_context.confidence >= self.min_confidence_threshold:
                # 新しいコンテキストを追跡に追加
                self.active_contexts[terminal_id] = new_context

                # 次のアクションを予測
                await self._predict_next_actions(new_context)

                return self._create_result_from_context(terminal_id, new_context)

            return self._create_empty_result(terminal_id)

        except Exception as e:
            self.logger.error(f"Failed to infer operation context: {e}")
            return self._create_empty_result(terminal_id)

    async def _get_recent_commands(self, terminal_id: str) -> List[Dict]:
        """最近のコマンド履歴を取得"""
        try:
            query = """
            SELECT command, timestamp, output_text, error_level, metadata
            FROM terminal_logs 
            WHERE terminal_id = ? AND log_type = 'COMMAND'
            ORDER BY timestamp DESC 
            LIMIT ?
            """

            results = await self.sql_storage.fetch_all(
                query, [terminal_id, self.recent_commands_window]
            )

            # 時系列順に並び替え
            return list(reversed(results))

        except Exception as e:
            self.logger.error(f"Failed to get recent commands: {e}")
            return []

    async def _check_existing_context(
        self, terminal_id: str, recent_commands: List[Dict]
    ) -> Optional[OperationContext]:
        """既存のコンテキストをチェック"""
        existing = self.active_contexts.get(terminal_id)

        if not existing:
            return None

        # タイムアウトチェック
        elapsed = (datetime.utcnow() - existing.start_time).total_seconds()
        if elapsed > self.context_timeout:
            # コンテキストを履歴に移動
            self._archive_context(terminal_id, existing)
            return None

        return existing

    async def _update_existing_context(
        self, context: OperationContext, recent_commands: List[Dict]
    ) -> OperationContext:
        """既存コンテキストを更新"""
        try:
            # コマンド履歴を更新
            new_commands = [cmd["command"] for cmd in recent_commands]
            context.command_sequence = new_commands[-self.recent_commands_window :]

            # ステージを更新
            context.stage = await self._determine_operation_stage(context, recent_commands)

            # 進捗を計算
            context.progress_percentage = await self._calculate_progress(context)

            # リスク要因を分析
            context.risk_factors = await self._analyze_risk_factors(context, recent_commands)

            self.logger.debug(f"Updated context for {context.terminal_id}: {context.stage}")
            return context

        except Exception as e:
            self.logger.error(f"Failed to update context: {e}")
            return context

    async def _infer_new_context(
        self, terminal_id: str, recent_commands: List[Dict]
    ) -> Optional[OperationContext]:
        """新しいコンテキストを推定"""
        try:
            # コマンドシーケンスをテキスト化
            command_sequence = [cmd["command"] for cmd in recent_commands]
            command_text = " → ".join(command_sequence)

            # ベクトル検索で類似パターンを取得
            similar_patterns = await self.vector_storage.similarity_search(
                query=command_text,
                filters={"pattern_type": "learned_operation"},
                limit=5,
                threshold=0.6,
            )

            if not similar_patterns:
                return await self._fallback_inference(terminal_id, command_sequence)

            # 最も類似度の高いパターンを選択
            best_match = similar_patterns[0]
            confidence = best_match[1]  # 類似度スコア

            # パターンの詳細を取得
            pattern_metadata = await self._get_pattern_metadata(best_match[0])

            if not pattern_metadata:
                return await self._fallback_inference(terminal_id, command_sequence)

            # オペレーションコンテキストを作成
            operation_type = OperationType(pattern_metadata.get("operation_type", "unknown"))

            context = OperationContext(
                terminal_id=terminal_id,
                operation_type=operation_type,
                stage=OperationStage.IN_PROGRESS,
                confidence=confidence,
                start_time=datetime.utcnow(),
                command_sequence=command_sequence,
                estimated_duration=pattern_metadata.get("average_duration"),
                metadata={
                    "matched_pattern_id": best_match[0],
                    "pattern_frequency": pattern_metadata.get("frequency", 0),
                    "pattern_success_rate": pattern_metadata.get("success_rate", 0.0),
                },
            )

            self.logger.info(
                f"Inferred new context for {terminal_id}: {operation_type.value} "
                f"(confidence: {confidence:.2f})"
            )

            return context

        except Exception as e:
            self.logger.error(f"Failed to infer new context: {e}")
            return None

    async def _fallback_inference(
        self, terminal_id: str, command_sequence: List[str]
    ) -> Optional[OperationContext]:
        """フォールバック推定（パターンマッチングベース）"""
        try:
            # 簡単なキーワードベース推定
            command_text = " ".join(command_sequence).lower()

            operation_type = OperationType.UNKNOWN
            confidence = 0.3

            # キーワードベース分類
            if any(word in command_text for word in ["deploy", "build", "production"]):
                operation_type = OperationType.DEPLOYMENT
                confidence = 0.4
            elif any(word in command_text for word in ["test", "spec", "coverage"]):
                operation_type = OperationType.TESTING
                confidence = 0.4
            elif any(word in command_text for word in ["debug", "error", "tail", "grep"]):
                operation_type = OperationType.DEBUGGING
                confidence = 0.4
            elif any(word in command_text for word in ["git", "commit", "push", "checkout"]):
                operation_type = OperationType.DEVELOPMENT
                confidence = 0.4

            if operation_type != OperationType.UNKNOWN:
                return OperationContext(
                    terminal_id=terminal_id,
                    operation_type=operation_type,
                    stage=OperationStage.IN_PROGRESS,
                    confidence=confidence,
                    start_time=datetime.utcnow(),
                    command_sequence=command_sequence,
                    metadata={"inference_method": "fallback_keywords"},
                )

            return None

        except Exception as e:
            self.logger.error(f"Fallback inference failed: {e}")
            return None

    async def _get_pattern_metadata(self, pattern_id: str) -> Optional[Dict]:
        """パターンのメタデータを取得"""
        try:
            # VectorDBからメタデータを取得
            # 実際の実装ではVectorStorageAdapterにget_metadata メソッドが必要
            # ここではダミー実装
            return {
                "operation_type": "development",
                "frequency": 10,
                "success_rate": 0.8,
                "average_duration": 600,
            }

        except Exception as e:
            self.logger.error(f"Failed to get pattern metadata: {e}")
            return None

    async def _determine_operation_stage(
        self, context: OperationContext, recent_commands: List[Dict]
    ) -> OperationStage:
        """オペレーションの段階を判定"""
        try:
            # 最新のコマンドとその結果を分析
            if not recent_commands:
                return context.stage

            latest_command = recent_commands[-1]
            error_level = latest_command.get("error_level", "INFO")
            output = latest_command.get("output_text", "").lower()

            # エラーが発生している場合
            if error_level == "ERROR":
                return OperationStage.FAILED

            # 成功指標をチェック
            success_indicators = [
                "success",
                "complete",
                "done",
                "finished",
                "deployed",
                "passed",
                "ok",
                "successful",
            ]

            if any(indicator in output for indicator in success_indicators):
                return OperationStage.COMPLETING

            # テスト/検証段階の検出
            test_keywords = ["test", "verify", "check", "validate"]
            if any(
                keyword in latest_command.get("command", "").lower() for keyword in test_keywords
            ):
                return OperationStage.VALIDATING

            return OperationStage.IN_PROGRESS

        except Exception as e:
            self.logger.error(f"Failed to determine stage: {e}")
            return context.stage

    async def _calculate_progress(self, context: OperationContext) -> float:
        """進捗率を計算"""
        try:
            # 時間ベースの進捗計算
            if context.estimated_duration:
                elapsed = (datetime.utcnow() - context.start_time).total_seconds()
                time_progress = min(elapsed / context.estimated_duration, 1.0)
            else:
                time_progress = 0.0

            # ステージベースの進捗
            stage_progress = {
                OperationStage.STARTING: 0.1,
                OperationStage.IN_PROGRESS: 0.5,
                OperationStage.VALIDATING: 0.8,
                OperationStage.COMPLETING: 0.9,
                OperationStage.COMPLETED: 1.0,
                OperationStage.FAILED: 0.0,
            }.get(context.stage, 0.0)

            # 重み付き平均
            progress = (time_progress * 0.3) + (stage_progress * 0.7)
            return min(progress, 1.0)

        except Exception as e:
            self.logger.error(f"Failed to calculate progress: {e}")
            return 0.0

    async def _analyze_risk_factors(
        self, context: OperationContext, recent_commands: List[Dict]
    ) -> List[str]:
        """リスク要因を分析"""
        risk_factors = []

        try:
            # エラー率の確認
            error_count = sum(1 for cmd in recent_commands if cmd.get("error_level") == "ERROR")
            if error_count > 0:
                risk_factors.append(f"Recent errors detected ({error_count} commands)")

            # 長時間実行の検出
            elapsed = (datetime.utcnow() - context.start_time).total_seconds()
            if context.estimated_duration and elapsed > context.estimated_duration * 1.5:
                risk_factors.append("Operation taking longer than expected")

            # 危険なコマンドの検出
            dangerous_patterns = ["rm -rf", "sudo rm", "DROP TABLE", "DELETE FROM"]
            for cmd in recent_commands:
                command = cmd.get("command", "")
                if any(pattern in command for pattern in dangerous_patterns):
                    risk_factors.append("Potentially dangerous command detected")
                    break

            return risk_factors

        except Exception as e:
            self.logger.error(f"Failed to analyze risk factors: {e}")
            return []

    async def _predict_next_actions(self, context: OperationContext) -> None:
        """次のアクションを予測"""
        try:
            # パターンベースの予測
            if context.metadata.get("matched_pattern_id"):
                # 類似パターンから次のコマンドを予測
                next_commands = await self._get_pattern_next_commands(
                    context.metadata["matched_pattern_id"]
                )
                context.next_likely_commands = next_commands[:3]

            # ルールベースの予測
            if not context.next_likely_commands:
                context.next_likely_commands = await self._rule_based_prediction(context)

            # 提案アクションの生成
            context.suggested_actions = await self._generate_suggestions(context)

        except Exception as e:
            self.logger.error(f"Failed to predict next actions: {e}")

    async def _get_pattern_next_commands(self, pattern_id: str) -> List[str]:
        """パターンから次のコマンドを予測"""
        # 実装略：VectorDBから類似パターンの後続コマンドを取得
        return ["git status", "npm test", "git commit"]

    async def _rule_based_prediction(self, context: OperationContext) -> List[str]:
        """ルールベースの次アクション予測"""
        predictions = []

        if context.operation_type == OperationType.DEVELOPMENT:
            if "git add" in context.command_sequence:
                predictions.append("git commit")
            elif "git commit" in context.command_sequence:
                predictions.append("git push")

        elif context.operation_type == OperationType.DEPLOYMENT:
            if "npm run build" in context.command_sequence:
                predictions.extend(["npm test", "pm2 restart"])

        return predictions

    async def _generate_suggestions(self, context: OperationContext) -> List[str]:
        """提案アクションを生成"""
        suggestions = []

        # ステージベースの提案
        if context.stage == OperationStage.IN_PROGRESS:
            suggestions.append("Consider running tests before proceeding")

        # リスクベースの提案
        if context.risk_factors:
            suggestions.append("Review recent errors before continuing")

        return suggestions

    def _archive_context(self, terminal_id: str, context: OperationContext) -> None:
        """コンテキストを履歴にアーカイブ"""
        if terminal_id not in self.context_history:
            self.context_history[terminal_id] = []

        context.stage = OperationStage.COMPLETED
        self.context_history[terminal_id].append(context)

        # 履歴サイズ制限
        if len(self.context_history[terminal_id]) > 100:
            self.context_history[terminal_id] = self.context_history[terminal_id][-50:]

        # アクティブコンテキストから削除
        self.active_contexts.pop(terminal_id, None)

    def _create_result_from_context(
        self, terminal_id: str, context: OperationContext
    ) -> ContextInferenceResult:
        """コンテキストから結果を作成"""
        return ContextInferenceResult(
            terminal_id=terminal_id,
            timestamp=datetime.utcnow(),
            primary_context=context,
            overall_confidence=context.confidence,
            reasoning=[
                f"Matched operation type: {context.operation_type.value}",
                f"Current stage: {context.stage.value}",
                f"Progress: {context.progress_percentage:.1%}",
            ],
            matched_patterns=[context.metadata.get("matched_pattern_id", "")],
            recommendations=context.suggested_actions,
            warnings=context.risk_factors,
        )

    def _create_empty_result(self, terminal_id: str) -> ContextInferenceResult:
        """空の結果を作成"""
        return ContextInferenceResult(
            terminal_id=terminal_id,
            timestamp=datetime.utcnow(),
            primary_context=OperationContext(
                terminal_id=terminal_id,
                operation_type=OperationType.UNKNOWN,
                stage=OperationStage.STARTING,
                confidence=0.0,
                start_time=datetime.utcnow(),
            ),
            overall_confidence=0.0,
            reasoning=["No sufficient command history for inference"],
        )
