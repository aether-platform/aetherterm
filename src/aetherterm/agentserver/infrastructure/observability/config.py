"""
OpenTelemetry Configuration Management

Handles configuration for Grafana Cloud APM integration.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class GrafanaCloudConfig:
    """Configuration for Grafana Cloud integration."""

    # Grafana Cloud credentials
    instance_id: Optional[str] = field(
        default_factory=lambda: os.getenv("GRAFANA_CLOUD_INSTANCE_ID")
    )
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("GRAFANA_CLOUD_API_KEY"))

    # OTLP endpoints
    traces_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("GRAFANA_CLOUD_OTLP_ENDPOINT")
    )
    metrics_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("GRAFANA_CLOUD_METRICS_ENDPOINT")
    )
    logs_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("GRAFANA_CLOUD_LOGS_ENDPOINT")
    )

    # Service information
    service_name: str = "aetherterm-agentserver"
    service_version: str = "0.0.1"
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # OpenTelemetry settings
    enable_tracing: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLE_TRACING", "true").lower() == "true"
    )
    enable_metrics: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLE_METRICS", "true").lower() == "true"
    )
    enable_logging: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLE_LOGGING", "true").lower() == "true"
    )
    enable_console_exporter: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLE_CONSOLE", "false").lower() == "true"
    )

    # Sampling configuration
    trace_sample_rate: float = field(
        default_factory=lambda: float(os.getenv("OTEL_TRACE_SAMPLE_RATE", "1.0"))
    )

    # Batch settings
    max_export_batch_size: int = field(
        default_factory=lambda: int(os.getenv("OTEL_MAX_EXPORT_BATCH_SIZE", "512"))
    )
    export_timeout_millis: int = field(
        default_factory=lambda: int(os.getenv("OTEL_EXPORT_TIMEOUT_MILLIS", "30000"))
    )

    def __post_init__(self):
        """Post-initialization setup."""
        # Auto-generate endpoints if instance_id is provided
        if self.instance_id and not self.traces_endpoint:
            region = "prod-us-central-0"  # Default region
            self.traces_endpoint = f"https://tempo-{region}.grafana.net/tempo"

        if self.instance_id and not self.metrics_endpoint:
            region = "prod-us-central-0"  # Default region
            self.metrics_endpoint = f"https://prometheus-{region}.grafana.net/api/prom/push"

        if self.instance_id and not self.logs_endpoint:
            region = "prod-us-central-0"  # Default region
            self.logs_endpoint = f"https://logs-{region}.grafana.net/loki/api/v1/push"

    @property
    def is_enabled(self) -> bool:
        """Check if Grafana Cloud integration is enabled."""
        return bool(self.api_key and (self.traces_endpoint or self.metrics_endpoint))

    @property
    def auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Grafana Cloud."""
        if not self.api_key:
            return {}

        return {"Authorization": f"Basic {self.api_key}"}

    def to_otel_config(self) -> Dict[str, Any]:
        """Convert to OpenTelemetry configuration dictionary."""
        config = {
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "enable_tracing": self.enable_tracing,
            "enable_metrics": self.enable_metrics,
            "enable_logging": self.enable_logging,
            "enable_console_exporter": self.enable_console_exporter,
            "trace_sample_rate": self.trace_sample_rate,
            "max_export_batch_size": self.max_export_batch_size,
            "export_timeout_millis": self.export_timeout_millis,
        }

        if self.is_enabled:
            config.update(
                {
                    "grafana_cloud_instance_id": self.instance_id,
                    "grafana_cloud_api_key": self.api_key,
                    "otlp_traces_endpoint": self.traces_endpoint,
                    "otlp_metrics_endpoint": self.metrics_endpoint,
                    "otlp_logs_endpoint": self.logs_endpoint,
                }
            )

        return config


def load_grafana_config() -> GrafanaCloudConfig:
    """Load Grafana Cloud configuration from environment."""
    return GrafanaCloudConfig()


def setup_environment_variables():
    """Setup example environment variables for Grafana Cloud."""
    example_env = """
# Grafana Cloud APM Configuration
# Replace with your actual Grafana Cloud credentials

# Your Grafana Cloud instance ID
export GRAFANA_CLOUD_INSTANCE_ID="your-instance-id"

# Your Grafana Cloud API key (with push permissions)
export GRAFANA_CLOUD_API_KEY="your-api-key"

# Environment (development, staging, production)
export ENVIRONMENT="development"

# OpenTelemetry settings
export OTEL_ENABLE_TRACING="true"
export OTEL_ENABLE_METRICS="true"
export OTEL_ENABLE_LOGGING="true"
export OTEL_ENABLE_CONSOLE="false"
export OTEL_TRACE_SAMPLE_RATE="1.0"

# Optional: Custom OTLP endpoints (auto-generated if not set)
# export GRAFANA_CLOUD_OTLP_ENDPOINT="https://otlp-gateway-prod-us-central-0.grafana.net/otlp"
# export GRAFANA_CLOUD_METRICS_ENDPOINT="https://prometheus-prod-us-central-0.grafana.net/api/prom/push"
# export GRAFANA_CLOUD_LOGS_ENDPOINT="https://logs-prod-us-central-0.grafana.net/loki/api/v1/push"
"""

    print("Example environment variables for Grafana Cloud APM:")
    print(example_env)

    # Write to .env.example file
    env_file = os.path.join(os.getcwd(), ".env.example")
    with open(env_file, "w") as f:
        f.write(example_env)

    print(f"Example configuration written to: {env_file}")


if __name__ == "__main__":
    setup_environment_variables()
