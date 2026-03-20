"""Sandbox backend protocol and auto-detection."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Protocol, runtime_checkable

log = logging.getLogger("agiterm.sandbox")

CRI_SOCKET = os.environ.get("CRI_SOCKET", "unix:///run/containerd/containerd.sock")


@runtime_checkable
class SandboxBackend(Protocol):
    """CRI sandbox interface."""

    @property
    def backend_type(self) -> str: ...

    async def prepare(
        self,
        username: str,
        session_id: str,
        image: str,
        env: dict[str, str],
        runtime_handler: str = "",
    ) -> None:
        """Ensure sandbox container is running for this user."""
        ...

    def wrap_command(self, username: str, cmd: list[str]) -> list[str]:
        """Wrap a tool command to run inside the sandbox."""
        ...

    async def cleanup(self, username: str, session_id: str) -> None:
        """Stop and remove sandbox for this user/session."""
        ...

    async def cleanup_all(self) -> None:
        """Stop all sandboxes (shutdown)."""
        ...


def _cri_socket_path() -> str:
    """Extract filesystem path from CRI_SOCKET URI."""
    sock = CRI_SOCKET
    if sock.startswith("unix://"):
        sock = sock[len("unix://"):]
    return sock


def _check_cri() -> None:
    """Verify CRI runtime is available. Raises RuntimeError if not."""
    sock = _cri_socket_path()
    if not os.path.exists(sock):
        raise RuntimeError(
            f"CRI socket not found at {sock}. "
            "containerd must be running. Set CRI_SOCKET env to override."
        )
    if not shutil.which("crictl"):
        raise RuntimeError(
            "crictl not found in PATH. "
            "Install crictl: https://github.com/kubernetes-sigs/cri-tools"
        )


def create_backend() -> SandboxBackend:
    """Create the CRI sandbox backend. Raises RuntimeError if unavailable."""
    _check_cri()

    from aetherterm.agiterm.sandbox.cri import CriBackend

    log.info("CRI sandbox backend initialized at %s", CRI_SOCKET)
    return CriBackend()
