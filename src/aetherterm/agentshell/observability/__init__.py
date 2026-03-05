"""AetherTerm Shell Observability Package

OpenTelemetryを使用した分散トレーシング、メトリクス収集、
構造化ログ出力を提供します。
"""

from .logger import StructuredLogger
from .telemetry import TelemetryManager
from .tracer import DistributedTracer


def setup_telemetry(
    service_name: str = "aetherterm-shell",
    service_version: str = "0.2.0",
    environment: str = "development",
    otlp_endpoint: str = None,
    enable_console_export: bool = True,
) -> TelemetryManager:
    """テレメトリーシステムをセットアップして初期化済みのTelemetryManagerを返す

    Args:
        service_name: サービス名
        service_version: サービスバージョン
        environment: 環境名
        otlp_endpoint: OTLPエンドポイント
        enable_console_export: コンソール出力を有効にするか

    Returns:
        初期化済みのTelemetryManager
    """
    telemetry_manager = TelemetryManager(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        otlp_endpoint=otlp_endpoint,
        enable_console_export=enable_console_export,
    )
    telemetry_manager.initialize()
    return telemetry_manager


__all__ = [
    "DistributedTracer",
    "StructuredLogger",
    "TelemetryManager",
    "setup_telemetry",
]
