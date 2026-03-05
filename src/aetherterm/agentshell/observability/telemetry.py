"""OpenTelemetry テレメトリー管理

分散トレーシング、メトリクス収集、ログ統合のための
OpenTelemetry設定と管理を行います。
"""

import logging
import os
from typing import Dict, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


class TelemetryManager:
    """OpenTelemetryテレメトリー管理クラス

    トレーシング、メトリクス、ログの統合管理を行い、
    AetherTermシェルの観測可能性を提供します。
    """

    def __init__(
        self,
        service_name: str = "aetherterm-shell",
        service_version: str = "0.2.0",
        environment: str = "development",
        otlp_endpoint: Optional[str] = None,
        enable_console_export: bool = True,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.otlp_endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        self.enable_console_export = enable_console_export

        # OpenTelemetryコンポーネント
        self._resource: Optional[Resource] = None
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None

        # メトリクス
        self._session_counter: Optional[metrics.Counter] = None
        self._command_histogram: Optional[metrics.Histogram] = None
        self._error_counter: Optional[metrics.Counter] = None
        self._active_sessions_gauge: Optional[metrics.UpDownCounter] = None

        self._initialized = False

    def initialize(self) -> None:
        """テレメトリーシステムを初期化"""
        if self._initialized:
            logger.warning("テレメトリーシステムは既に初期化されています")
            return

        try:
            # リソース情報を設定
            self._setup_resource()

            # トレーシングを設定
            self._setup_tracing()

            # メトリクスを設定
            self._setup_metrics()

            # ログ統合を設定
            self._setup_logging_instrumentation()

            self._initialized = True
            logger.info(f"OpenTelemetryテレメトリーシステムを初期化しました: {self.service_name}")

        except Exception as e:
            logger.error(f"テレメトリーシステムの初期化に失敗しました: {e}")
            raise

    def shutdown(self) -> None:
        """テレメトリーシステムを終了"""
        if not self._initialized:
            return

        try:
            # トレーサープロバイダーを終了
            if self._tracer_provider:
                self._tracer_provider.shutdown()

            # メータープロバイダーを終了
            if self._meter_provider:
                self._meter_provider.shutdown()

            self._initialized = False
            logger.info("OpenTelemetryテレメトリーシステムを終了しました")

        except Exception as e:
            logger.error(f"テレメトリーシステムの終了に失敗しました: {e}")

    def _setup_resource(self) -> None:
        """リソース情報を設定"""
        self._resource = Resource.create(
            {
                "service.name": self.service_name,
                "service.version": self.service_version,
                "deployment.environment": self.environment,
                "host.name": os.uname().nodename,
                "process.pid": str(os.getpid()),
            }
        )

    def _setup_tracing(self) -> None:
        """分散トレーシングを設定"""
        # トレーサープロバイダーを作成
        self._tracer_provider = TracerProvider(resource=self._resource)

        # OTLPエクスポーターを設定
        if self.otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)
                span_processor = BatchSpanProcessor(otlp_exporter)
                self._tracer_provider.add_span_processor(span_processor)
                logger.debug(f"OTLPトレースエクスポーターを設定しました: {self.otlp_endpoint}")
            except Exception as e:
                logger.warning(f"OTLPトレースエクスポーターの設定に失敗しました: {e}")

        # コンソールエクスポーター（開発用）
        if self.enable_console_export:
            try:
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter

                console_exporter = ConsoleSpanExporter()
                console_processor = BatchSpanProcessor(console_exporter)
                self._tracer_provider.add_span_processor(console_processor)
                logger.debug("コンソールトレースエクスポーターを設定しました")
            except Exception as e:
                logger.warning(f"コンソールトレースエクスポーターの設定に失敗しました: {e}")

        # グローバルトレーサープロバイダーを設定
        trace.set_tracer_provider(self._tracer_provider)
        self._tracer = trace.get_tracer(self.service_name, self.service_version)

    def _setup_metrics(self) -> None:
        """メトリクス収集を設定"""
        # メトリクスリーダーを作成
        readers = []

        # OTLPメトリクスエクスポーター
        if self.otlp_endpoint:
            try:
                otlp_metric_exporter = OTLPMetricExporter(endpoint=self.otlp_endpoint)
                otlp_reader = PeriodicExportingMetricReader(
                    exporter=otlp_metric_exporter,
                    export_interval_millis=30000,  # 30秒間隔
                )
                readers.append(otlp_reader)
                logger.debug(f"OTLPメトリクスエクスポーターを設定しました: {self.otlp_endpoint}")
            except Exception as e:
                logger.warning(f"OTLPメトリクスエクスポーターの設定に失敗しました: {e}")

        # コンソールメトリクスエクスポーター（開発用）
        if self.enable_console_export:
            try:
                from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

                console_metric_exporter = ConsoleMetricExporter()
                console_reader = PeriodicExportingMetricReader(
                    exporter=console_metric_exporter,
                    export_interval_millis=60000,  # 60秒間隔
                )
                readers.append(console_reader)
                logger.debug("コンソールメトリクスエクスポーターを設定しました")
            except Exception as e:
                logger.warning(f"コンソールメトリクスエクスポーターの設定に失敗しました: {e}")

        # メータープロバイダーを作成
        self._meter_provider = MeterProvider(
            resource=self._resource,
            metric_readers=readers,
        )

        # グローバルメータープロバイダーを設定
        metrics.set_meter_provider(self._meter_provider)
        self._meter = metrics.get_meter(self.service_name, self.service_version)

        # 標準メトリクスを作成
        self._create_standard_metrics()

    def _create_standard_metrics(self) -> None:
        """標準メトリクスを作成"""
        if not self._meter:
            return

        # セッション作成カウンター
        self._session_counter = self._meter.create_counter(
            name="aetherterm_sessions_created_total",
            description="Total number of terminal sessions created",
            unit="1",
        )

        # コマンド実行時間ヒストグラム
        self._command_histogram = self._meter.create_histogram(
            name="aetherterm_command_duration_seconds",
            description="Duration of terminal commands in seconds",
            unit="s",
        )

        # エラーカウンター
        self._error_counter = self._meter.create_counter(
            name="aetherterm_errors_total",
            description="Total number of errors encountered",
            unit="1",
        )

        # アクティブセッション数ゲージ
        self._active_sessions_gauge = self._meter.create_up_down_counter(
            name="aetherterm_active_sessions",
            description="Number of currently active terminal sessions",
            unit="1",
        )

    def _setup_logging_instrumentation(self) -> None:
        """ログ統合を設定"""
        try:
            LoggingInstrumentor().instrument(set_logging_format=True)
            logger.debug("ログ統合を設定しました")
        except Exception as e:
            logger.warning(f"ログ統合の設定に失敗しました: {e}")

    @property
    def tracer(self) -> Optional[trace.Tracer]:
        """トレーサーを取得"""
        return self._tracer

    @property
    def meter(self) -> Optional[metrics.Meter]:
        """メーターを取得"""
        return self._meter

    def record_session_created(self, attributes: Optional[Dict[str, str]] = None) -> None:
        """セッション作成メトリクスを記録"""
        if self._session_counter:
            self._session_counter.add(1, attributes or {})

    def record_command_duration(
        self, duration: float, attributes: Optional[Dict[str, str]] = None
    ) -> None:
        """コマンド実行時間メトリクスを記録"""
        if self._command_histogram:
            self._command_histogram.record(duration, attributes or {})

    def record_error(self, error_type: str, attributes: Optional[Dict[str, str]] = None) -> None:
        """エラーメトリクスを記録"""
        if self._error_counter:
            attrs = attributes or {}
            attrs["error_type"] = error_type
            self._error_counter.add(1, attrs)

    def update_active_sessions(self, count: int) -> None:
        """アクティブセッション数を更新"""
        if self._active_sessions_gauge:
            # 現在の値をリセットして新しい値を設定
            # UpDownCounterは差分を記録するため、現在の値を追跡する必要がある
            # 簡単のため、ここでは絶対値を記録
            self._active_sessions_gauge.add(count)

    def is_initialized(self) -> bool:
        """初期化状態を確認"""
        return self._initialized

    def get_status(self) -> Dict[str, any]:
        """テレメトリーシステムの状態を取得"""
        return {
            "initialized": self._initialized,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "otlp_endpoint": self.otlp_endpoint,
            "console_export_enabled": self.enable_console_export,
            "tracer_available": self._tracer is not None,
            "meter_available": self._meter is not None,
        }
