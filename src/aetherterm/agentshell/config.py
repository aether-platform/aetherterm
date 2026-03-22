"""設定管理モジュール

ラッパープログラムの設定を管理し、TOML設定ファイルの読み込みと
環境変数の処理を行います。
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib


@dataclass
class AIServiceConfig:
    """AI サービス設定（独立化対応）"""

    # AIプロバイダー設定
    provider: str = "openai"  # openai, anthropic, local
    api_key: Optional[str] = None
    model: str = "gpt-4"
    endpoint: Optional[str] = (
        None  # カスタムエンドポイント（プロバイダーのデフォルトを使用する場合はNone）
    )

    # 接続設定
    timeout: int = 30
    max_retries: int = 3

    # 機能設定
    enable_command_analysis: bool = True
    enable_error_suggestions: bool = True
    enable_command_suggestions: bool = True
    max_command_history: int = 50


@dataclass
class MonitorConfig:
    """ターミナル監視設定"""

    buffer_size: int = 8192
    poll_interval: float = 0.1
    max_history: int = 1000
    enable_output_capture: bool = True
    enable_input_capture: bool = False


@dataclass
class SessionConfig:
    """セッション管理設定"""

    session_timeout: int = 3600  # 1時間
    max_sessions: int = 100
    cleanup_interval: int = 300  # 5分
    enable_persistence: bool = True


@dataclass
class LoggingConfig:
    """ログ設定"""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class TelemetryConfig:
    """OpenTelemetry設定"""

    service_name: str = "aetherterm-wrapper"
    service_version: str = "1.0.0"
    environment: str = "development"
    otlp_endpoint: str = "http://localhost:4317"
    enable_tracing: bool = True
    enable_metrics: bool = True
    enable_log_instrumentation: bool = True
    trace_sample_rate: float = 1.0
    metrics_export_interval: int = 30


@dataclass
class ServerConnectionConfig:
    """AetherTermサーバー接続設定（オプショナル）"""

    enabled: bool = False  # デフォルトは無効
    server_url: str = "http://localhost:57575"
    auto_connect: bool = True
    sync_interval: int = 30
    reconnection_attempts: int = 5
    reconnection_delay: int = 1

    # 同期機能設定
    sync_sessions: bool = True
    sync_ai_notifications: bool = True
    sync_command_history: bool = False  # プライバシー考慮でデフォルトOFF



@dataclass
class WrapperConfig:
    """ラッパープログラム全体設定（独立化対応）"""

    # 動作モード設定
    mode: str = "standalone"  # standalone, connected
    debug: bool = False

    # AI機能設定
    enable_ai: bool = True
    ai_service: AIServiceConfig = field(default_factory=AIServiceConfig)

    # サーバー連携設定（オプショナル）
    server_connection: ServerConnectionConfig = field(default_factory=ServerConnectionConfig)

    # その他のサービス設定
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    # レガシー互換性
    wrapper_socket_path: str = "/tmp/aetherterm_wrapper.sock"

    # レガシー互換性のためのプロパティ
    @property
    def aetherterm_sync(self) -> ServerConnectionConfig:
        """レガシー互換性のためのプロパティ"""
        return self.server_connection

    @classmethod
    def load_from_file(cls, config_path: Optional[Path] = None) -> "WrapperConfig":
        """設定ファイルから設定を読み込む

        Args:
            config_path: 設定ファイルのパス（Noneの場合はデフォルトパスを使用）

        Returns:
            WrapperConfig: 読み込まれた設定
        """
        if config_path is None:
            config_path = Path(__file__).parent / "wrapper.toml"

        if not config_path.exists():
            logging.warning(f"設定ファイルが見つかりません: {config_path}")
            return cls()

        try:
            with open(config_path, "rb") as f:
                config_data = tomllib.load(f)

            return cls._from_dict(config_data)

        except Exception as e:
            logging.error(f"設定ファイルの読み込みに失敗しました: {e}")
            return cls()

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "WrapperConfig":
        """辞書から設定オブジェクトを作成"""
        config = cls()

        # AI サービス設定
        if "ai_service" in data:
            ai_data = data["ai_service"]
            config.ai_service = AIServiceConfig(
                provider=ai_data.get("provider", config.ai_service.provider),
                api_key=ai_data.get("api_key", config.ai_service.api_key),
                model=ai_data.get("model", config.ai_service.model),
                endpoint=ai_data.get("endpoint", config.ai_service.endpoint),
                timeout=ai_data.get("timeout", config.ai_service.timeout),
                max_retries=ai_data.get("max_retries", config.ai_service.max_retries),
                enable_command_analysis=ai_data.get(
                    "enable_command_analysis", config.ai_service.enable_command_analysis
                ),
                enable_error_suggestions=ai_data.get(
                    "enable_error_suggestions", config.ai_service.enable_error_suggestions
                ),
                enable_command_suggestions=ai_data.get(
                    "enable_command_suggestions", config.ai_service.enable_command_suggestions
                ),
                max_command_history=ai_data.get(
                    "max_command_history", config.ai_service.max_command_history
                ),
            )

        # 監視設定
        if "monitor" in data:
            monitor_data = data["monitor"]
            config.monitor = MonitorConfig(
                buffer_size=monitor_data.get("buffer_size", config.monitor.buffer_size),
                poll_interval=monitor_data.get("poll_interval", config.monitor.poll_interval),
                max_history=monitor_data.get("max_history", config.monitor.max_history),
                enable_output_capture=monitor_data.get(
                    "enable_output_capture", config.monitor.enable_output_capture
                ),
                enable_input_capture=monitor_data.get(
                    "enable_input_capture", config.monitor.enable_input_capture
                ),
            )

        # セッション設定
        if "session" in data:
            session_data = data["session"]
            config.session = SessionConfig(
                session_timeout=session_data.get("session_timeout", config.session.session_timeout),
                max_sessions=session_data.get("max_sessions", config.session.max_sessions),
                cleanup_interval=session_data.get(
                    "cleanup_interval", config.session.cleanup_interval
                ),
                enable_persistence=session_data.get(
                    "enable_persistence", config.session.enable_persistence
                ),
            )

        # ログ設定
        if "logging" in data:
            logging_data = data["logging"]
            config.logging = LoggingConfig(
                level=logging_data.get("level", config.logging.level),
                format=logging_data.get("format", config.logging.format),
                file_path=logging_data.get("file_path", config.logging.file_path),
                max_file_size=logging_data.get("max_file_size", config.logging.max_file_size),
                backup_count=logging_data.get("backup_count", config.logging.backup_count),
            )

        # テレメトリー設定
        if "telemetry" in data:
            telemetry_data = data["telemetry"]
            config.telemetry = TelemetryConfig(
                service_name=telemetry_data.get("service_name", config.telemetry.service_name),
                service_version=telemetry_data.get(
                    "service_version", config.telemetry.service_version
                ),
                environment=telemetry_data.get("environment", config.telemetry.environment),
                otlp_endpoint=telemetry_data.get("otlp_endpoint", config.telemetry.otlp_endpoint),
                enable_tracing=telemetry_data.get(
                    "enable_tracing", config.telemetry.enable_tracing
                ),
                enable_metrics=telemetry_data.get(
                    "enable_metrics", config.telemetry.enable_metrics
                ),
                enable_log_instrumentation=telemetry_data.get(
                    "enable_log_instrumentation", config.telemetry.enable_log_instrumentation
                ),
                trace_sample_rate=telemetry_data.get(
                    "trace_sample_rate", config.telemetry.trace_sample_rate
                ),
                metrics_export_interval=telemetry_data.get(
                    "metrics_export_interval", config.telemetry.metrics_export_interval
                ),
            )

        # サーバー接続設定（新設計）
        if "server_connection" in data:
            server_data = data["server_connection"]
            config.server_connection = ServerConnectionConfig(
                enabled=server_data.get("enabled", config.server_connection.enabled),
                server_url=server_data.get("server_url", config.server_connection.server_url),
                auto_connect=server_data.get("auto_connect", config.server_connection.auto_connect),
                sync_interval=server_data.get(
                    "sync_interval", config.server_connection.sync_interval
                ),
                reconnection_attempts=server_data.get(
                    "reconnection_attempts", config.server_connection.reconnection_attempts
                ),
                reconnection_delay=server_data.get(
                    "reconnection_delay", config.server_connection.reconnection_delay
                ),
                sync_sessions=server_data.get(
                    "sync_sessions", config.server_connection.sync_sessions
                ),
                sync_ai_notifications=server_data.get(
                    "sync_ai_notifications", config.server_connection.sync_ai_notifications
                ),
                sync_command_history=server_data.get(
                    "sync_command_history", config.server_connection.sync_command_history
                ),
            )

        # レガシー互換性: aetherterm_sync設定
        if "aetherterm_sync" in data:
            sync_data = data["aetherterm_sync"]
            config.server_connection = ServerConnectionConfig(
                enabled=sync_data.get("enable_sync", config.server_connection.enabled),
                server_url=sync_data.get("server_url", config.server_connection.server_url),
                auto_connect=True,
                sync_interval=sync_data.get(
                    "sync_interval", config.server_connection.sync_interval
                ),
                reconnection_attempts=sync_data.get(
                    "reconnection_attempts", config.server_connection.reconnection_attempts
                ),
                reconnection_delay=sync_data.get(
                    "reconnection_delay", config.server_connection.reconnection_delay
                ),
                sync_sessions=True,
                sync_ai_notifications=True,
                sync_command_history=False,
            )

        # 全体設定
        config.mode = data.get("mode", config.mode)
        config.debug = data.get("debug", config.debug)
        config.enable_ai = data.get("enable_ai", config.enable_ai)
        config.wrapper_socket_path = data.get("wrapper_socket_path", config.wrapper_socket_path)

        return config

    def apply_environment_overrides(self) -> None:
        """環境変数による設定の上書き（独立化対応）"""
        # 動作モード設定
        if os.getenv("AETHERTERM_MODE"):
            mode = os.getenv("AETHERTERM_MODE").lower()
            if mode in ["standalone", "connected"]:
                self.mode = mode

        # AI サービス設定
        if os.getenv("AETHERTERM_AI_PROVIDER"):
            provider = os.getenv("AETHERTERM_AI_PROVIDER").lower()
            if provider in ["openai", "anthropic", "local"]:
                self.ai_service.provider = provider

        if os.getenv("AETHERTERM_AI_ENDPOINT"):
            self.ai_service.endpoint = os.getenv("AETHERTERM_AI_ENDPOINT")
        if os.getenv("AETHERTERM_AI_API_KEY"):
            self.ai_service.api_key = os.getenv("AETHERTERM_AI_API_KEY")
        if os.getenv("AETHERTERM_AI_MODEL"):
            self.ai_service.model = os.getenv("AETHERTERM_AI_MODEL")

        # デバッグ設定
        if os.getenv("AETHERTERM_DEBUG"):
            self.debug = os.getenv("AETHERTERM_DEBUG").lower() in ("true", "1", "yes")

        # AI機能の有効/無効
        if os.getenv("AETHERTERM_ENABLE_AI"):
            self.enable_ai = os.getenv("AETHERTERM_ENABLE_AI").lower() in ("true", "1", "yes")

        # テレメトリー設定
        if os.getenv("AETHERTERM_OTLP_ENDPOINT"):
            self.telemetry.otlp_endpoint = os.getenv("AETHERTERM_OTLP_ENDPOINT")
        if os.getenv("AETHERTERM_SERVICE_NAME"):
            self.telemetry.service_name = os.getenv("AETHERTERM_SERVICE_NAME")
        if os.getenv("AETHERTERM_ENVIRONMENT"):
            self.telemetry.environment = os.getenv("AETHERTERM_ENVIRONMENT")

        # サーバー接続設定
        if os.getenv("AETHERTERM_SERVER_ENABLED"):
            self.server_connection.enabled = os.getenv("AETHERTERM_SERVER_ENABLED").lower() in (
                "true",
                "1",
                "yes",
            )
        if os.getenv("AETHERTERM_SERVER_URL"):
            self.server_connection.server_url = os.getenv("AETHERTERM_SERVER_URL")

        # レガシー互換性
        if os.getenv("AETHERTERM_ENABLE_SYNC"):
            self.server_connection.enabled = os.getenv("AETHERTERM_ENABLE_SYNC").lower() in (
                "true",
                "1",
                "yes",
            )

        # モード設定の自動調整
        if self.server_connection.enabled and self.mode == "standalone":
            self.mode = "connected"
        elif not self.server_connection.enabled and self.mode == "connected":
            self.mode = "standalone"

    def setup_logging(self) -> None:
        """ログ設定を適用"""
        log_level = getattr(logging, self.logging.level.upper(), logging.INFO)

        handlers = []

        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(self.logging.format))
        handlers.append(console_handler)

        # ファイルハンドラー（設定されている場合）
        if self.logging.file_path:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                self.logging.file_path,
                maxBytes=self.logging.max_file_size,
                backupCount=self.logging.backup_count,
            )
            file_handler.setFormatter(logging.Formatter(self.logging.format))
            handlers.append(file_handler)

        # ログ設定を適用
        logging.basicConfig(level=log_level, handlers=handlers, force=True)

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
