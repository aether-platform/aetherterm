"""テレメトリーサービス

OpenTelemetry連携による分散トレーシング、ログ収集、メトリクス収集機能を提供し、
ターミナルイベント、AI連携、セッション管理の各操作をトレースします。
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from ..config import TelemetryConfig

logger = logging.getLogger(__name__)


class TelemetryService:
    """テレメトリーサービス

    分散トレーシング、メトリクス収集、ログ相関機能を提供
    """

    def __init__(self, config: TelemetryConfig):
        self.config = config
        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None
        self._initialized = False

        # メトリクス
        self._session_counter = None
        self._terminal_event_counter = None
        self._ai_request_counter = None
        self._ai_request_duration = None
        self._session_duration = None

    def initialize(self) -> None:
        """OpenTelemetryを初期化"""
        if self._initialized:
            return

        try:
            # リソース情報を設定
            resource = Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: self.config.service_name,
                    ResourceAttributes.SERVICE_VERSION: self.config.service_version,
                    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self.config.environment,
                    ResourceAttributes.HOST_NAME: os.uname().nodename,
                    ResourceAttributes.PROCESS_PID: os.getpid(),
                }
            )

            # トレーシングの初期化
            if self.config.enable_tracing:
                self._setup_tracing(resource)

            # メトリクスの初期化
            if self.config.enable_metrics:
                self._setup_metrics(resource)

            # ログ計装の初期化
            if self.config.enable_log_instrumentation:
                self._setup_logging()

            self._initialized = True
            logger.info("OpenTelemetry初期化完了")

        except Exception as e:
            logger.error(f"OpenTelemetry初期化に失敗しました: {e}")
            raise

    def _setup_tracing(self, resource: Resource) -> None:
        """トレーシングを設定"""
        # TracerProviderを設定
        tracer_provider = TracerProvider(resource=resource)

        # OTLP Exporterを設定
        otlp_exporter = OTLPSpanExporter(
            endpoint=self.config.otlp_endpoint,
        )

        # BatchSpanProcessorを追加
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        # グローバルTracerProviderを設定
        trace.set_tracer_provider(tracer_provider)

        # Tracerを取得
        self._tracer = trace.get_tracer(self.config.service_name, self.config.service_version)

    def _setup_metrics(self, resource: Resource) -> None:
        """メトリクスを設定"""
        # OTLP Metric Exporterを設定
        metric_exporter = OTLPMetricExporter(
            endpoint=self.config.otlp_endpoint,
        )

        # PeriodicExportingMetricReaderを設定
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=self.config.metrics_export_interval * 1000,
        )

        # MeterProviderを設定
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )

        # グローバルMeterProviderを設定
        metrics.set_meter_provider(meter_provider)

        # Meterを取得
        self._meter = metrics.get_meter(self.config.service_name, self.config.service_version)

        # メトリクスを作成
        self._create_metrics()

    def _setup_logging(self) -> None:
        """ログ計装を設定"""
        LoggingInstrumentor().instrument(set_logging_format=True)

    def _create_metrics(self) -> None:
        """メトリクスを作成"""
        if not self._meter:
            return

        # セッション関連メトリクス
        self._session_counter = self._meter.create_counter(
            name="aetherterm_sessions_total",
            description="Total number of terminal sessions",
            unit="1",
        )

        self._session_duration = self._meter.create_histogram(
            name="aetherterm_session_duration_seconds",
            description="Duration of terminal sessions",
            unit="s",
        )

        # ターミナルイベント関連メトリクス
        self._terminal_event_counter = self._meter.create_counter(
            name="aetherterm_terminal_events_total",
            description="Total number of terminal events",
            unit="1",
        )

        # AI関連メトリクス
        self._ai_request_counter = self._meter.create_counter(
            name="aetherterm_ai_requests_total", description="Total number of AI requests", unit="1"
        )

        self._ai_request_duration = self._meter.create_histogram(
            name="aetherterm_ai_request_duration_seconds",
            description="Duration of AI requests",
            unit="s",
        )

    @contextmanager
    def trace_operation(self, operation_name: str, attributes: Optional[Dict[str, Any]] = None):
        """操作をトレースするコンテキストマネージャー

        Args:
            operation_name: 操作名
            attributes: 追加属性
        """
        if not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(operation_name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def trace_session_event(self, event_type: str, session_id: str, **attributes):
        """セッションイベントをトレース"""
        with self.trace_operation(
            f"session.{event_type}",
            {"session.id": session_id, "session.event_type": event_type, **attributes},
        ) as span:
            # セッションメトリクスを記録
            if self._session_counter:
                self._session_counter.add(1, {"event_type": event_type, "session_id": session_id})

    def trace_terminal_event(
        self, event_type: str, session_id: str, data_size: int = 0, **attributes
    ):
        """ターミナルイベントをトレース"""
        with self.trace_operation(
            f"terminal.{event_type}",
            {
                "terminal.session_id": session_id,
                "terminal.event_type": event_type,
                "terminal.data_size": data_size,
                **attributes,
            },
        ) as span:
            # ターミナルイベントメトリクスを記録
            if self._terminal_event_counter:
                self._terminal_event_counter.add(
                    1, {"event_type": event_type, "session_id": session_id}
                )

    def trace_ai_request(self, request_type: str, model: str = None, **attributes):
        """AI リクエストをトレース"""
        start_time = time.time()

        with self.trace_operation(
            f"ai.{request_type}", {"ai.request_type": request_type, "ai.model": model, **attributes}
        ) as span:
            try:
                yield span
            finally:
                # AI リクエストメトリクスを記録
                duration = time.time() - start_time

                if self._ai_request_counter:
                    self._ai_request_counter.add(
                        1, {"request_type": request_type, "model": model or "unknown"}
                    )

                if self._ai_request_duration:
                    self._ai_request_duration.record(
                        duration, {"request_type": request_type, "model": model or "unknown"}
                    )

    def record_session_duration(self, session_id: str, duration_seconds: float, **attributes):
        """セッション継続時間を記録"""
        if self._session_duration:
            self._session_duration.record(
                duration_seconds, {"session_id": session_id, **attributes}
            )

    def add_session_attributes(self, session_id: str, attributes: Dict[str, Any]):
        """現在のスパンにセッション属性を追加"""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_attribute("session.id", session_id)
            for key, value in attributes.items():
                current_span.set_attribute(f"session.{key}", value)

    def log_structured(self, level: str, message: str, **extra):
        """構造化ログを出力"""
        log_method = getattr(logger, level.lower(), logger.info)

        # トレース情報を追加
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            extra.update(
                {
                    "trace_id": format(span_context.trace_id, "032x"),
                    "span_id": format(span_context.span_id, "016x"),
                }
            )

        log_method(message, extra=extra)

    def shutdown(self):
        """OpenTelemetryをシャットダウン"""
        if not self._initialized:
            return

        try:
            # TracerProviderをシャットダウン
            if hasattr(trace.get_tracer_provider(), "shutdown"):
                trace.get_tracer_provider().shutdown()

            # MeterProviderをシャットダウン
            if hasattr(metrics.get_meter_provider(), "shutdown"):
                metrics.get_meter_provider().shutdown()

            logger.info("OpenTelemetryシャットダウン完了")

        except Exception as e:
            logger.error(f"OpenTelemetryシャットダウンに失敗しました: {e}")

    def is_initialized(self) -> bool:
        """初期化済みかどうかを確認"""
        return self._initialized
