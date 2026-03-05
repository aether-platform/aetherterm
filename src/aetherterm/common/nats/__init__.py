"""
AetherTerm NATS messaging infrastructure.

Provides shared NATS connection management and messaging primitives
used by AgentServer, ControlServer, and other components.
"""

from .client import NatsClient
from .subjects import Subjects

__all__ = ["NatsClient", "Subjects"]
