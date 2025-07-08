"""
Custom Metrics for AetherTerm APM

Defines application-specific metrics for monitoring AetherTerm performance.
"""

from typing import Optional
from opentelemetry.metrics import Counter, Histogram, Gauge
from .telemetry import get_meter


class AetherTermMetrics:
    """Custom metrics for AetherTerm monitoring."""

    def __init__(self, meter_name: str = "aetherterm.agentserver"):
        self.meter = get_meter(meter_name)
        self._setup_metrics()

    def _setup_metrics(self):
        """Initialize all custom metrics."""

        # Terminal session metrics
        self.terminal_sessions_active = self.meter.create_gauge(
            name="aetherterm.terminal.sessions.active",
            description="Number of active terminal sessions",
            unit="1",
        )

        self.terminal_sessions_created_total = self.meter.create_counter(
            name="aetherterm.terminal.sessions.created.total",
            description="Total number of terminal sessions created",
            unit="1",
        )

        self.terminal_sessions_duration = self.meter.create_histogram(
            name="aetherterm.terminal.sessions.duration",
            description="Duration of terminal sessions",
            unit="s",
        )

        # WebSocket connection metrics
        self.websocket_connections_active = self.meter.create_gauge(
            name="aetherterm.websocket.connections.active",
            description="Number of active WebSocket connections",
            unit="1",
        )

        self.websocket_messages_sent_total = self.meter.create_counter(
            name="aetherterm.websocket.messages.sent.total",
            description="Total number of WebSocket messages sent",
            unit="1",
        )

        self.websocket_messages_received_total = self.meter.create_counter(
            name="aetherterm.websocket.messages.received.total",
            description="Total number of WebSocket messages received",
            unit="1",
        )

        # AI agent metrics
        self.ai_requests_total = self.meter.create_counter(
            name="aetherterm.ai.requests.total",
            description="Total number of AI agent requests",
            unit="1",
        )

        self.ai_request_duration = self.meter.create_histogram(
            name="aetherterm.ai.request.duration",
            description="Duration of AI agent requests",
            unit="s",
        )

        self.ai_token_usage_total = self.meter.create_counter(
            name="aetherterm.ai.tokens.usage.total",
            description="Total number of AI tokens used",
            unit="1",
        )

        # System resource metrics
        self.system_memory_usage = self.meter.create_gauge(
            name="aetherterm.system.memory.usage", description="System memory usage", unit="bytes"
        )

        self.system_cpu_usage = self.meter.create_gauge(
            name="aetherterm.system.cpu.usage",
            description="System CPU usage percentage",
            unit="percent",
        )

        # Log processing metrics
        self.log_lines_processed_total = self.meter.create_counter(
            name="aetherterm.logs.lines.processed.total",
            description="Total number of log lines processed",
            unit="1",
        )

        self.log_analysis_duration = self.meter.create_histogram(
            name="aetherterm.logs.analysis.duration",
            description="Duration of log analysis operations",
            unit="s",
        )

        # Error metrics
        self.errors_total = self.meter.create_counter(
            name="aetherterm.errors.total", description="Total number of errors", unit="1"
        )

    # Terminal session tracking methods
    def record_terminal_session_created(self, session_type: str = "terminal"):
        """Record a new terminal session creation."""
        self.terminal_sessions_created_total.add(1, {"session_type": session_type})

    def update_active_terminal_sessions(self, count: int):
        """Update the count of active terminal sessions."""
        self.terminal_sessions_active.set(count)

    def record_terminal_session_duration(
        self, duration_seconds: float, session_type: str = "terminal"
    ):
        """Record the duration of a terminal session."""
        self.terminal_sessions_duration.record(duration_seconds, {"session_type": session_type})

    # WebSocket tracking methods
    def record_websocket_message_sent(self, message_type: str = "output"):
        """Record a WebSocket message sent."""
        self.websocket_messages_sent_total.add(1, {"message_type": message_type})

    def record_websocket_message_received(self, message_type: str = "input"):
        """Record a WebSocket message received."""
        self.websocket_messages_received_total.add(1, {"message_type": message_type})

    def update_active_websocket_connections(self, count: int):
        """Update the count of active WebSocket connections."""
        self.websocket_connections_active.set(count)

    # AI agent tracking methods
    def record_ai_request(self, agent_type: str = "chat", status: str = "success"):
        """Record an AI agent request."""
        self.ai_requests_total.add(1, {"agent_type": agent_type, "status": status})

    def record_ai_request_duration(self, duration_seconds: float, agent_type: str = "chat"):
        """Record the duration of an AI agent request."""
        self.ai_request_duration.record(duration_seconds, {"agent_type": agent_type})

    def record_ai_token_usage(self, token_count: int, token_type: str = "total"):
        """Record AI token usage."""
        self.ai_token_usage_total.add(token_count, {"token_type": token_type})

    # System resource tracking methods
    def update_memory_usage(self, bytes_used: int):
        """Update system memory usage."""
        self.system_memory_usage.set(bytes_used)

    def update_cpu_usage(self, percentage: float):
        """Update system CPU usage."""
        self.system_cpu_usage.set(percentage)

    # Log processing tracking methods
    def record_log_lines_processed(self, count: int, log_type: str = "system"):
        """Record the number of log lines processed."""
        self.log_lines_processed_total.add(count, {"log_type": log_type})

    def record_log_analysis_duration(self, duration_seconds: float, analysis_type: str = "summary"):
        """Record the duration of log analysis."""
        self.log_analysis_duration.record(duration_seconds, {"analysis_type": analysis_type})

    # Error tracking methods
    def record_error(self, error_type: str = "general", severity: str = "error"):
        """Record an error occurrence."""
        self.errors_total.add(1, {"error_type": error_type, "severity": severity})


# Global metrics instance
_metrics_instance: Optional[AetherTermMetrics] = None


def get_metrics() -> AetherTermMetrics:
    """Get the global metrics instance."""
    global _metrics_instance

    if _metrics_instance is None:
        _metrics_instance = AetherTermMetrics()

    return _metrics_instance


def initialize_metrics() -> AetherTermMetrics:
    """Initialize and return the global metrics instance."""
    return get_metrics()
