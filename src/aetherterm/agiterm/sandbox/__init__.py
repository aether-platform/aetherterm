"""CRI (containerd) sandbox for session isolation.

All sessions run inside CRI PodSandbox + Container.
Requires containerd and crictl.
"""

from aetherterm.agiterm.sandbox.backend import (
    SandboxBackend,
    create_backend,
)

__all__ = [
    "SandboxBackend",
    "create_backend",
]
