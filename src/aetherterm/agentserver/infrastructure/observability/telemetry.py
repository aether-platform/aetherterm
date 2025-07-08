"""
OpenTelemetry Configuration for Grafana Cloud APM

Configures distributed tracing, metrics, and logging for AetherTerm.
"""

import os
import logging
from typing import Optional
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

logger = logging.getLogger(__name__)


class GrafanaCloudTelemetry:
    """Grafana Cloud OpenTelemetry configuration manager."""

    def __init__(
        self,
        service_name: str = "aetherterm-agentserver",
        service_version: str = "0.0.1",
        environment: str = "development",
        grafana_cloud_instance_id: Optional[str] = None,
        grafana_cloud_api_key: Optional[str] = None,
        otlp_endpoint: Optional[str] = None,
        enable_console_exporter: bool = False,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.grafana_cloud_instance_id = grafana_cloud_instance_id or os.getenv(
            "GRAFANA_CLOUD_INSTANCE_ID"
        )
        self.grafana_cloud_api_key = grafana_cloud_api_key or os.getenv("GRAFANA_CLOUD_API_KEY")
        self.otlp_endpoint = otlp_endpoint or os.getenv("GRAFANA_CLOUD_OTLP_ENDPOINT")
        self.enable_console_exporter = enable_console_exporter

        # Build Grafana Cloud OTLP endpoint if not provided
        if not self.otlp_endpoint and self.grafana_cloud_instance_id:
            self.otlp_endpoint = f"https://otlp-gateway-{self.environment}.grafana.net/otlp"

        self._resource = None
        self._tracer_provider = None
        self._meter_provider = None

    def _create_resource(self) -> Resource:
        """Create OpenTelemetry resource with service information."""
        if self._resource is None:
            self._resource = Resource.create(
                {
                    "service.name": self.service_name,
                    "service.version": self.service_version,
                    "deployment.environment": self.environment,
                    "telemetry.sdk.language": "python",
                    "telemetry.sdk.name": "opentelemetry",
                }
            )
        return self._resource

    def setup_tracing(self) -> None:
        """Configure distributed tracing."""
        resource = self._create_resource()

        # Create tracer provider
        self._tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self._tracer_provider)

        # Configure OTLP exporter
        if self.otlp_endpoint and self.grafana_cloud_api_key:
            otlp_exporter = OTLPSpanExporter(
                endpoint=self.otlp_endpoint,
                headers={"Authorization": f"Basic {self.grafana_cloud_api_key}"},
            )
            self._tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"Configured OTLP span exporter for {self.otlp_endpoint}")

        # Console exporter for development
        if self.enable_console_exporter:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            console_exporter = ConsoleSpanExporter()
            self._tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Configured console span exporter")

    def setup_metrics(self) -> None:
        """Configure metrics collection."""
        resource = self._create_resource()

        # Configure OTLP metric exporter
        if self.otlp_endpoint and self.grafana_cloud_api_key:
            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=self.otlp_endpoint,
                headers={"Authorization": f"Basic {self.grafana_cloud_api_key}"},
            )

            # Create metric reader
            metric_reader = PeriodicExportingMetricReader(
                exporter=otlp_metric_exporter,
                export_interval_millis=60000,  # Export every 60 seconds
            )

            # Create meter provider
            self._meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(self._meter_provider)
            logger.info("Configured OTLP metric exporter")

        # Console exporter for development
        if self.enable_console_exporter:
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

            console_metric_exporter = ConsoleMetricExporter()
            console_reader = PeriodicExportingMetricReader(
                exporter=console_metric_exporter, export_interval_millis=60000
            )

            if self._meter_provider:
                # Add console reader to existing provider
                self._meter_provider._metric_readers.append(console_reader)
            else:
                # Create new provider with console reader
                self._meter_provider = MeterProvider(
                    resource=resource, metric_readers=[console_reader]
                )
                metrics.set_meter_provider(self._meter_provider)
            logger.info("Configured console metric exporter")

    def setup_logging(self) -> None:
        """Configure structured logging with trace correlation."""
        LoggingInstrumentor().instrument(set_logging_format=True, log_hook=self._log_hook)
        logger.info("Configured OpenTelemetry logging instrumentation")

    def _log_hook(self, span, record):
        """Add trace context to log records."""
        if span and span.is_recording():
            record.trace_id = format(span.get_span_context().trace_id, "032x")
            record.span_id = format(span.get_span_context().span_id, "016x")

    def instrument_app(self, app) -> None:
        """Instrument FastAPI application."""
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=self._tracer_provider,
            meter_provider=self._meter_provider,
            excluded_urls="healthz,metrics",  # Exclude health checks
        )
        logger.info("Instrumented FastAPI application")

    def instrument_libraries(self) -> None:
        """Instrument third-party libraries."""
        # SQLAlchemy instrumentation
        try:
            SQLAlchemyInstrumentor().instrument()
            logger.info("Instrumented SQLAlchemy")
        except Exception as e:
            logger.warning(f"Failed to instrument SQLAlchemy: {e}")

        # Redis instrumentation
        try:
            RedisInstrumentor().instrument()
            logger.info("Instrumented Redis")
        except Exception as e:
            logger.warning(f"Failed to instrument Redis: {e}")

        # aiohttp client instrumentation
        try:
            AioHttpClientInstrumentor().instrument()
            logger.info("Instrumented aiohttp client")
        except Exception as e:
            logger.warning(f"Failed to instrument aiohttp client: {e}")

    def setup_all(self, app=None) -> None:
        """Setup all OpenTelemetry instrumentation."""
        logger.info(f"Setting up OpenTelemetry for {self.service_name}")

        try:
            self.setup_tracing()
            self.setup_metrics()
            self.setup_logging()
            self.instrument_libraries()

            if app:
                self.instrument_app(app)

            logger.info("OpenTelemetry setup completed successfully")

        except Exception as e:
            logger.error(f"Failed to setup OpenTelemetry: {e}")
            raise

    def get_tracer(self, name: str = None):
        """Get a tracer instance."""
        return trace.get_tracer(name or self.service_name)

    def get_meter(self, name: str = None):
        """Get a meter instance."""
        return metrics.get_meter(name or self.service_name)


# Global telemetry instance
_telemetry_instance: Optional[GrafanaCloudTelemetry] = None


def initialize_telemetry(
    service_name: str = "aetherterm-agentserver", **kwargs
) -> GrafanaCloudTelemetry:
    """Initialize global telemetry instance."""
    global _telemetry_instance

    if _telemetry_instance is None:
        _telemetry_instance = GrafanaCloudTelemetry(service_name=service_name, **kwargs)

    return _telemetry_instance


def get_telemetry() -> Optional[GrafanaCloudTelemetry]:
    """Get the global telemetry instance."""
    return _telemetry_instance


def get_tracer(name: str = "aetherterm"):
    """Get a tracer instance."""
    if _telemetry_instance:
        return _telemetry_instance.get_tracer(name)
    return trace.get_tracer(name)


def get_meter(name: str = "aetherterm"):
    """Get a meter instance."""
    if _telemetry_instance:
        return _telemetry_instance.get_meter(name)
    return metrics.get_meter(name)
