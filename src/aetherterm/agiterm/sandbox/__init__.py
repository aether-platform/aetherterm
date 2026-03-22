"""Sandbox backends for session isolation.

Supports:
  - nsjail: lightweight process-level isolation (default when available)
  - CRI: containerd PodSandbox + Container (Kubernetes environments)

Set SANDBOX_BACKEND=nsjail|cri|auto (default: auto).
"""

from aetherterm.agiterm.sandbox.backend import (
    SandboxBackend,
    create_backend,
)

__all__ = [
    "SandboxBackend",
    "create_backend",
]
