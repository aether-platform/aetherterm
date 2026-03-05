"""ターミナル監視コントローラー

PTY通信とサービス層の橋渡しを行い、
ターミナルイベントの処理とAI連携を管理します。
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import MonitorConfig
from ..domain.models import EventType, TerminalEvent
from ..log_sender import LogSender
from ..pty.terminal_pty import TerminalPTY
from ..service.ai_service import AIService
from ..service.session_service import SessionService
from ..service.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)


class TerminalController:
    """ターミナル監視コントローラー

    PTY通信を管理し、AI連携とセッション管理サービスと連携して
    ターミナルイベントを処理します。
    """

    def __init__(
        self,
        config: MonitorConfig,
        session_id: str,
        ai_service: Optional[AIService] = None,
        session_service: Optional[SessionService] = None,
        telemetry_service: Optional[TelemetryService] = None,
        nats_bridge=None,
    ):
        self.config = config
        self.session_id = session_id
        self._ai_service = ai_service
        self._session_service = session_service
        self._telemetry_service = telemetry_service
        self._nats_bridge = nats_bridge

        # ログ送信（ControlServerへのターミナル出力転送）
        self._log_sender = LogSender(session_id=session_id)

        # PTY通信インスタンス
        self._pty = TerminalPTY(config, session_id)
        self._pty.add_event_callback(self._handle_terminal_event)

        # コマンド実行追跡
        self._current_command = ""
        self._command_start_time: Optional[datetime] = None
        self._last_prompt_time: Optional[datetime] = None

    async def start_monitoring(self, command: Optional[List[str]] = None) -> None:
        """監視を開始

        Args:
            command: 実行するコマンド（Noneの場合はシェルを起動）
        """
        logger.info(f"ターミナル監視を開始します: セッション {self.session_id}")

        # テレメトリーでセッション開始をトレース
        if self._telemetry_service:
            self._telemetry_service.trace_session_event("start", self.session_id)

        # ログ送信を開始（ControlServerへのターミナル出力転送）
        await self._log_sender.start()

        # PTY監視を開始
        await self._pty.start_monitoring(command)

        # NATS bridge を開始（設定されている場合）
        if self._nats_bridge:
            try:
                await self._nats_bridge.start(self._pty)
            except Exception as e:
                logger.warning(f"NATS bridge の開始に失敗しました（続行します）: {e}")

        # セッションサービスにセッション作成を通知
        if self._session_service:
            child_pid = self._pty.get_child_pid()
            if child_pid:
                self._session_service.create_session(
                    pid=child_pid,
                    terminal_size=(24, 80),  # デフォルトサイズ
                    metadata={"controller": "terminal_controller"},
                    aetherterm_session_id=self.session_id,  # AetherTermセッションIDとして使用
                )

    async def stop_monitoring(self) -> None:
        """監視を停止"""
        logger.info(f"ターミナル監視を停止します: セッション {self.session_id}")

        # テレメトリーでセッション終了をトレース
        if self._telemetry_service:
            self._telemetry_service.trace_session_event("stop", self.session_id)

        # NATS bridge を停止
        if self._nats_bridge:
            try:
                await self._nats_bridge.stop()
            except Exception as e:
                logger.warning(f"NATS bridge の停止に失敗しました: {e}")

        # ログ送信を停止
        await self._log_sender.stop()

        # PTY監視を停止
        await self._pty.stop_monitoring()

        # セッションサービスにセッション削除を通知
        if self._session_service:
            self._session_service.remove_session(self.session_id)

    async def _handle_terminal_event(self, event: TerminalEvent) -> None:
        """ターミナルイベントを処理

        Args:
            event: ターミナルイベント
        """
        try:
            # テレメトリーでイベントをトレース
            if self._telemetry_service:
                self._telemetry_service.trace_terminal_event(
                    event.event_type.value, event.session_id, len(event.data)
                )

            # 出力イベントの場合はAI分析を実行
            if event.event_type == EventType.OUTPUT:
                await self._log_sender.send_output(event.data)
                await self._analyze_terminal_output(event)

            # セッションサービスに活動を通知
            if self._session_service:
                session = self._session_service.get_session(event.session_id)
                if session:
                    session.update_activity()

        except Exception as e:
            logger.error(f"ターミナルイベント処理エラー: {e}")

    async def _analyze_terminal_output(self, event: TerminalEvent) -> None:
        """ターミナル出力を分析

        Args:
            event: ターミナルイベント
        """
        try:
            # 出力内容をテキストに変換
            output_text = event.data.decode("utf-8", errors="replace")

            # エラーパターンを検出
            if self._is_error_output(output_text):
                # AI連携が有効な場合は通知を送信
                if self._ai_service and self._ai_service.is_running():
                    await self._ai_service.send_error_notification(
                        session_id=event.session_id,
                        error_type="output_error",
                        message="ターミナル出力でエラーが検出されました",
                        context={"output": output_text[:500]},  # 最初の500文字のみ
                    )

            # コマンド実行完了の検出
            if self._is_command_completion(output_text):
                await self._handle_command_completion(event.session_id, output_text)

        except Exception as e:
            logger.error(f"ターミナル出力分析エラー: {e}")

    def _is_error_output(self, output: str) -> bool:
        """エラー出力かどうかを判定

        Args:
            output: 出力内容

        Returns:
            bool: エラー出力の場合True
        """
        error_patterns = [
            r"error:",
            r"failed",
            r"permission denied",
            r"command not found",
            r"no such file",
            r"connection refused",
            r"timeout",
            r"segmentation fault",
            r"core dumped",
        ]

        output_lower = output.lower()
        for pattern in error_patterns:
            if re.search(pattern, output_lower):
                return True

        return False

    async def _handle_command_completion(self, session_id: str, output: str) -> None:
        """コマンド完了を処理

        Args:
            session_id: セッションID
            output: 出力内容
        """
        # コマンド実行時間を計算
        execution_time = 0.0
        if self._command_start_time:
            execution_time = (datetime.now() - self._command_start_time).total_seconds()

        # 終了コードを推定（簡易版）
        exit_code = 1 if self._is_error_output(output) else 0

        # 最後に実行されたコマンドを取得
        last_command = self._current_command or "unknown_command"

        if self._ai_service and self._ai_service.is_running():
            await self._ai_service.report_command_execution(
                session_id=session_id,
                command=last_command,
                output=output,
                exit_code=exit_code,
                execution_time=execution_time,
            )

        # 次のコマンドのために状態をリセット
        self._current_command = ""
        self._command_start_time = None

    def _is_command_completion(self, output: str) -> bool:
        """コマンド完了を検出

        Args:
            output: 出力内容

        Returns:
            bool: コマンド完了の場合True
        """
        # プロンプトの検出（簡易版）
        prompt_patterns = [
            r"\$\s*$",  # $ で終わる
            r"#\s*$",  # # で終わる
            r">\s*$",  # > で終わる
        ]

        for pattern in prompt_patterns:
            if re.search(pattern, output.strip()):
                self._last_prompt_time = datetime.now()
                return True

        return False

    def track_command_input(self, command: str) -> None:
        """コマンド入力を追跡

        Args:
            command: 入力されたコマンド
        """
        self._current_command = command.strip()
        self._command_start_time = datetime.now()

    async def send_input(self, data: bytes) -> bool:
        """ターミナルに入力を送信

        Args:
            data: 送信するデータ

        Returns:
            bool: 送信に成功した場合True
        """
        return await self._pty.send_input(data)

    async def resize_terminal(self, rows: int, cols: int) -> bool:
        """ターミナルサイズを変更

        Args:
            rows: 行数
            cols: 列数

        Returns:
            bool: 変更に成功した場合True
        """
        success = await self._pty.resize_terminal(rows, cols)

        # セッションサービスにサイズ変更を通知
        if success and self._session_service:
            self._session_service.update_session(self.session_id, terminal_size=(rows, cols))

        return success

    def get_current_screen(self) -> str:
        """現在の画面内容を取得"""
        return self._pty.get_current_screen()

    def get_recent_output(self, lines: int = 10) -> str:
        """最近の出力を取得"""
        return self._pty.get_recent_output(lines)

    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        return self._pty.get_stats()

    def is_monitoring(self) -> bool:
        """監視中かどうかを確認"""
        return self._pty.is_monitoring()

    def get_child_pid(self) -> Optional[int]:
        """子プロセスのPIDを取得"""
        return self._pty.get_child_pid()

    def is_child_running(self) -> bool:
        """子プロセスが実行中かどうかを確認"""
        return self._pty.is_child_running()

    def set_ai_service(self, ai_service: AIService) -> None:
        """AI連携サービスを設定"""
        self._ai_service = ai_service

    def set_session_service(self, session_service: SessionService) -> None:
        """セッション管理サービスを設定"""
        self._session_service = session_service

    def set_telemetry_service(self, telemetry_service: TelemetryService) -> None:
        """テレメトリーサービスを設定"""
        self._telemetry_service = telemetry_service
