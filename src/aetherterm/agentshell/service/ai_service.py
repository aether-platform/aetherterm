"""独立したAI連携サービス

直接AIプロバイダー（OpenAI、Anthropic等）と通信し、
AetherTermサーバーに依存しない独立したAI機能を提供します。
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from ..config import AIServiceConfig
from ..domain.models import ErrorNotification, Severity, WarningNotification
from .ai_providers import AIProvider, create_ai_provider

logger = logging.getLogger(__name__)


class IndependentAIService:
    """独立したAI連携サービス

    AIプロバイダーと直接通信し、サーバーに依存しない
    AI機能を提供します。サーバー連携はオプショナルです。
    """

    def __init__(
        self,
        config: AIServiceConfig,
        provider_type: str = "openai",
    ):
        self.config = config
        self.provider_type = provider_type

        self._is_running = False
        self._notification_callbacks: List[Callable] = []
        self._ai_provider: Optional[AIProvider] = None
        self._command_history: List[str] = []
        self._max_history = 50

        # ローカルエラーパターン（AIが利用できない場合のフォールバック）
        self._error_patterns = []

    async def start(self) -> None:
        """独立AI連携を開始"""
        if self._is_running:
            return

        logger.info("独立AI連携を開始します")

        try:
            # AIプロバイダーを初期化
            self._ai_provider = create_ai_provider(
                provider_type=self.provider_type,
                api_key=self.config.api_key or "",
                model=self.config.model,
                endpoint=self.config.endpoint
                if self.config.endpoint != "http://localhost:57575"
                else None,
            )

            self._is_running = True
            logger.info(f"独立AI連携が開始されました（プロバイダー: {self.provider_type}）")

        except Exception as e:
            logger.error(f"AI連携の開始に失敗しました: {e}")
            logger.info("ローカル解析モードで動作します")
            self._ai_provider = None
            self._is_running = True

    async def stop(self) -> None:
        """独立AI連携を停止"""
        if not self._is_running:
            return

        logger.info("独立AI連携を停止します")

        self._is_running = False
        self._ai_provider = None

        logger.info("独立AI連携が停止されました")

    async def analyze_command_with_ai(
        self, command: str, output: str, exit_code: int, execution_time: float
    ) -> Dict[str, Any]:
        """AIを使用してコマンドを解析

        Args:
            command: 実行されたコマンド
            output: コマンドの出力
            exit_code: 終了コード
            execution_time: 実行時間

        Returns:
            Dict[str, Any]: AI解析結果
        """
        if not self._ai_provider:
            logger.debug("AIプロバイダーが利用できません。ローカル解析を使用します。")
            return self._analyze_command_locally(command, output, exit_code, execution_time)

        try:
            context = {
                "execution_time": execution_time,
                "command_history": self._command_history[-5:],  # 最新5件
                "environment": "linux_terminal",
            }

            result = await self._ai_provider.analyze_command_output(
                command=command,
                output=output,
                exit_code=exit_code,
                context=context,
            )

            # コマンド履歴を更新
            self._add_to_history(command)

            return result

        except Exception as e:
            logger.error(f"AI解析に失敗しました: {e}")
            return self._analyze_command_locally(command, output, exit_code, execution_time)

    def _analyze_command_locally(
        self, command: str, output: str, exit_code: int, execution_time: float
    ) -> Dict[str, Any]:
        """コマンドをローカルで簡易解析（フォールバック）

        Args:
            command: 実行されたコマンド
            output: コマンドの出力
            exit_code: 終了コード
            execution_time: 実行時間

        Returns:
            Dict[str, Any]: ローカル解析結果
        """
        return {
            "success": exit_code == 0,
            "severity": "low",
            "summary": f"コマンド '{command}' の実行結果",
            "insights": [],
            "warnings": [],
            "recommendations": [],
            "error_patterns": [],
            "execution_time": execution_time,
        }

    async def suggest_error_fix(
        self, command: str, error_output: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """エラーの修正提案を取得

        Args:
            command: 実行されたコマンド
            error_output: エラー出力
            context: 追加のコンテキスト

        Returns:
            Dict[str, Any]: 修正提案
        """
        if not self._ai_provider:
            return {"error": "AIプロバイダーが利用できません", "suggestions": []}

        try:
            result = await self._ai_provider.suggest_error_fix(
                command=command,
                error_output=error_output,
                context=context or {},
            )
            return result

        except Exception as e:
            logger.error(f"エラー修正提案の取得に失敗しました: {e}")
            return {"error": str(e), "suggestions": []}

    async def suggest_next_commands(self, current_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """次のコマンドを提案

        Args:
            current_context: 現在のコンテキスト

        Returns:
            Dict[str, Any]: コマンド提案
        """
        if not self._ai_provider:
            return {"error": "AIプロバイダーが利用できません", "suggestions": []}

        try:
            result = await self._ai_provider.suggest_next_commands(
                command_history=self._command_history,
                current_context=current_context or {},
            )
            return result

        except Exception as e:
            logger.error(f"コマンド提案の取得に失敗しました: {e}")
            return {"error": str(e), "suggestions": []}

    async def is_command_dangerous(self, command: str) -> bool:
        """AIを使用してコマンドが危険かどうかを判定します。

        Args:
            command: 実行されたコマンド

        Returns:
            bool: コマンドが危険な場合はTrue
        """
        if not self._ai_provider:
            return False

        try:
            result = await self._ai_provider.is_command_dangerous(command=command)
            return result

        except Exception as e:
            logger.error(f"コマンド危険度判定の取得に失敗しました: {e}")
            return False

    def _add_to_history(self, command: str) -> None:
        """コマンド履歴に追加"""
        self._command_history.append(command)
        if len(self._command_history) > self._max_history:
            self._command_history = self._command_history[-self._max_history :]

    async def send_error_notification(
        self,
        session_id: str,
        error_type: str,
        message: str,
        severity: Severity = Severity.MEDIUM,
        context: Dict[str, Any] = None,
    ) -> None:
        """エラー通知を送信

        Args:
            session_id: セッションID
            error_type: エラータイプ
            message: エラーメッセージ
            severity: 重要度
            context: 追加のコンテキスト
        """
        notification = ErrorNotification(
            session_id=session_id,
            error_type=error_type,
            message=message,
            severity=severity,
            context=context or {},
        )

        # 登録されたコールバックに通知
        for callback in self._notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback("error", notification)
                else:
                    callback("error", notification)
            except Exception as e:
                logger.error(f"エラー通知コールバックの実行に失敗しました: {e}")

        logger.warning(f"エラー通知: {error_type} - {message} (セッション: {session_id})")

    async def send_warning_notification(
        self,
        session_id: str,
        warning_type: str,
        message: str,
        suggestions: List[str] = None,
        context: Dict[str, Any] = None,
    ) -> None:
        """警告通知を送信

        Args:
            session_id: セッションID
            warning_type: 警告タイプ
            message: 警告メッセージ
            suggestions: 提案リスト
            context: 追加のコンテキスト
        """
        notification = WarningNotification(
            session_id=session_id,
            warning_type=warning_type,
            message=message,
            suggestions=suggestions or [],
            context=context or {},
        )

        # 登録されたコールバックに通知
        for callback in self._notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback("warning", notification)
                else:
                    callback("warning", notification)
            except Exception as e:
                logger.error(f"警告通知コールバックの実行に失敗しました: {e}")

        logger.info(f"警告通知: {warning_type} - {message} (セッション: {session_id})")

    def register_notification_callback(self, callback: Callable) -> None:
        """通知コールバックを登録

        Args:
            callback: 通知を受信するコールバック関数
        """
        if callback not in self._notification_callbacks:
            self._notification_callbacks.append(callback)

    def unregister_notification_callback(self, callback: Callable) -> None:
        """通知コールバックを解除

        Args:
            callback: 解除するコールバック関数
        """
        if callback in self._notification_callbacks:
            self._notification_callbacks.remove(callback)

    async def _listen_for_notifications(self) -> None:
        """他システムからの通知を受信"""
        while self._is_running:
            try:
                # 他システムからの通知を受信する処理
                # 実際の実装では、WebSocketやHTTPポーリングなどを使用
                await asyncio.sleep(5)  # 5秒間隔でチェック

                # デモ用の通知生成（実際の実装では削除）
                if self._is_running:
                    await self._check_system_notifications()

            except Exception as e:
                logger.error(f"通知受信中にエラーが発生しました: {e}")
                await asyncio.sleep(1)

    async def _check_system_notifications(self) -> None:
        """システム通知をチェック（デモ用）"""
        # 実際の実装では、他システムからの通知をチェック
        # ここではデモ用の処理のみ

    async def report_command_execution(
        self, session_id: str, command: str, output: str, exit_code: int, execution_time: float
    ) -> None:
        """コマンド実行結果を報告し、AI解析と通知を実行

        Args:
            session_id: セッションID
            command: 実行されたコマンド
            output: コマンドの出力
            exit_code: 終了コード
            execution_time: 実行時間
        """
        # AI解析を実行
        analysis = await self.analyze_command_with_ai(command, output, exit_code, execution_time)

        # エラーが検出された場合は通知を送信
        if not analysis.get("success", True) or exit_code != 0:
            await self.send_error_notification(
                session_id=session_id,
                error_type="command_error",
                message=f"コマンド '{command}' でエラーが発生しました (終了コード: {exit_code})",
                severity=Severity.HIGH if exit_code != 0 else Severity.MEDIUM,
                context={
                    "command": command,
                    "exit_code": exit_code,
                    "ai_analysis": analysis,
                    "execution_time": execution_time,
                },
            )

            # AIによるエラー修正提案を取得
            if exit_code != 0:
                fix_suggestions = await self.suggest_error_fix(command, output)
                if fix_suggestions.get("fixes"):
                    await self.send_warning_notification(
                        session_id=session_id,
                        warning_type="ai_suggestion",
                        message="AIによる修正提案があります",
                        suggestions=[fix["description"] for fix in fix_suggestions["fixes"][:3]],
                        context={"fix_suggestions": fix_suggestions},
                    )

        # 警告がある場合は通知を送信
        warnings = analysis.get("warnings", [])
        if warnings:
            for warning in warnings:
                await self.send_warning_notification(
                    session_id=session_id,
                    warning_type="performance" if "実行時間" in warning else "security",
                    message=warning,
                    context={
                        "command": command,
                        "execution_time": execution_time,
                        "ai_analysis": analysis,
                    },
                )


    def is_running(self) -> bool:
        """AI連携が実行中かどうかを確認"""
        return self._is_running

    def has_ai_provider(self) -> bool:
        """AIプロバイダーが利用可能かどうかを確認"""
        return self._ai_provider is not None

    def get_provider_type(self) -> str:
        """現在のAIプロバイダータイプを取得"""
        return self.provider_type

    def get_command_history(self) -> List[str]:
        """コマンド履歴を取得"""
        return self._command_history.copy()

    def clear_command_history(self) -> None:
        """コマンド履歴をクリア"""
        self._command_history.clear()

    def get_status(self) -> Dict[str, Any]:
        """AI連携の状態を取得"""
        return {
            "is_running": self._is_running,
            "provider_type": self.provider_type,
            "has_ai_provider": self.has_ai_provider(),
            "command_history_count": len(self._command_history),
            "notification_callbacks": len(self._notification_callbacks),
            "config": {
                "endpoint": self.config.endpoint,
                "model": self.config.model,
                "timeout": self.config.timeout,
            },
        }


# レガシー互換性のためのエイリアス
AIService = IndependentAIService
