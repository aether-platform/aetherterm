"""構造化ログ出力クラス

OpenTelemetryと統合された構造化ログ出力を提供し、
トレーシング情報と連携したログ記録を行います。
"""

import json
import logging
import sys
from datetime import datetime
from typing import Optional

from opentelemetry import trace


class StructuredLogger:
    """構造化ログ出力クラス

    JSON形式での構造化ログ出力と、OpenTelemetryトレーシング情報の
    自動付与を行います。
    """

    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
        enable_console: bool = True,
        enable_file: bool = False,
        file_path: Optional[str] = None,
        enable_tracing: bool = True,
    ):
        self.name = name
        self.enable_tracing = enable_tracing

        # 標準ロガーを作成
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # 既存のハンドラーをクリア
        self.logger.handlers.clear()

        # コンソールハンドラー
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(self._create_formatter())
            self.logger.addHandler(console_handler)

        # ファイルハンドラー
        if enable_file and file_path:
            try:
                file_handler = logging.FileHandler(file_path)
                file_handler.setFormatter(self._create_formatter())
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.error(f"ファイルハンドラーの作成に失敗しました: {e}")

    def _create_formatter(self) -> logging.Formatter:
        """構造化ログフォーマッターを作成"""
        return StructuredFormatter(enable_tracing=self.enable_tracing)

    def debug(self, message: str, **kwargs) -> None:
        """デバッグレベルログ"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """情報レベルログ"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """警告レベルログ"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """エラーレベルログ"""
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """クリティカルレベルログ"""
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
        self._log(logging.CRITICAL, message, **kwargs)

    def _log(self, level: int, message: str, **kwargs) -> None:
        """内部ログ記録メソッド"""
        # 追加情報を extra として渡す
        extra = {
            "structured_data": kwargs,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # トレーシング情報を追加
        if self.enable_tracing:
            span = trace.get_current_span()
            if span and span.is_recording():
                span_context = span.get_span_context()
                extra["trace_id"] = format(span_context.trace_id, "032x")
                extra["span_id"] = format(span_context.span_id, "016x")

        self.logger.log(level, message, extra=extra)

    def log_session_event(self, event_type: str, session_id: str, **kwargs) -> None:
        """セッションイベントログ"""
        self.info(f"Session {event_type}", event_type=event_type, session_id=session_id, **kwargs)

    def log_command_execution(
        self, command: str, duration: float, exit_code: int, session_id: str, **kwargs
    ) -> None:
        """コマンド実行ログ"""
        level = logging.INFO if exit_code == 0 else logging.WARNING
        self._log(
            level,
            f"Command executed: {command}",
            command=command,
            duration=duration,
            exit_code=exit_code,
            session_id=session_id,
            **kwargs,
        )

    def log_ai_interaction(
        self,
        interaction_type: str,
        prompt: str,
        response: Optional[str] = None,
        duration: Optional[float] = None,
        **kwargs,
    ) -> None:
        """AI連携ログ"""
        self.info(
            f"AI interaction: {interaction_type}",
            interaction_type=interaction_type,
            prompt=prompt[:100] + "..." if len(prompt) > 100 else prompt,
            response_length=len(response) if response else 0,
            duration=duration,
            **kwargs,
        )

    def log_performance_metric(
        self, metric_name: str, value: float, unit: str = "", **kwargs
    ) -> None:
        """パフォーマンスメトリクスログ"""
        self.info(
            f"Performance metric: {metric_name}",
            metric_name=metric_name,
            value=value,
            unit=unit,
            **kwargs,
        )

    def log_security_event(
        self, event_type: str, severity: str, description: str, **kwargs
    ) -> None:
        """セキュリティイベントログ"""
        level = {
            "low": logging.INFO,
            "medium": logging.WARNING,
            "high": logging.ERROR,
            "critical": logging.CRITICAL,
        }.get(severity.lower(), logging.WARNING)

        self._log(
            level,
            f"Security event: {event_type}",
            event_type=event_type,
            severity=severity,
            description=description,
            **kwargs,
        )


class StructuredFormatter(logging.Formatter):
    """構造化ログフォーマッター

    ログレコードをJSON形式で出力します。
    """

    def __init__(self, enable_tracing: bool = True):
        super().__init__()
        self.enable_tracing = enable_tracing

    def format(self, record: logging.LogRecord) -> str:
        """ログレコードをJSON形式でフォーマット"""
        # 基本ログ情報
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # プロセス情報
        log_data["process"] = {
            "pid": record.process,
            "thread": record.thread,
        }

        # 構造化データを追加
        if hasattr(record, "structured_data"):
            log_data.update(record.structured_data)

        # トレーシング情報を追加
        if self.enable_tracing:
            if hasattr(record, "trace_id"):
                log_data["trace_id"] = record.trace_id
            if hasattr(record, "span_id"):
                log_data["span_id"] = record.span_id

        # 例外情報を追加
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # JSON形式で出力
        try:
            return json.dumps(log_data, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as e:
            # JSON化に失敗した場合はフォールバック
            fallback_data = {
                "timestamp": log_data["timestamp"],
                "level": log_data["level"],
                "logger": log_data["logger"],
                "message": log_data["message"],
                "json_error": str(e),
            }
            return json.dumps(fallback_data, ensure_ascii=False, separators=(",", ":"))


class LoggerFactory:
    """ロガーファクトリー

    統一された設定でStructuredLoggerインスタンスを作成します。
    """

    _default_config = {
        "level": logging.INFO,
        "enable_console": True,
        "enable_file": False,
        "file_path": None,
        "enable_tracing": True,
    }

    @classmethod
    def create_logger(self, name: str, **kwargs) -> StructuredLogger:
        """構造化ロガーを作成"""
        config = self._default_config.copy()
        config.update(kwargs)
        return StructuredLogger(name, **config)

    @classmethod
    def configure_defaults(self, **kwargs) -> None:
        """デフォルト設定を更新"""
        self._default_config.update(kwargs)

    @classmethod
    def create_session_logger(self, session_id: str) -> StructuredLogger:
        """セッション専用ロガーを作成"""
        return self.create_logger(f"aetherterm.session.{session_id}")

    @classmethod
    def create_ai_logger(self) -> StructuredLogger:
        """AI連携専用ロガーを作成"""
        return self.create_logger("aetherterm.ai")

    @classmethod
    def create_telemetry_logger(self) -> StructuredLogger:
        """テレメトリー専用ロガーを作成"""
        return self.create_logger("aetherterm.telemetry")
