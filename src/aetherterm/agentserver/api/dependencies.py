"""FastAPI dependency injection helpers for AgentServer routes.

Usage in route handlers::

    from .dependencies import TmuxRegistryDep, ControlBridgeDep, ControlHandlerDep

    @router.get("/health")
    async def health(
        tmux_registry: TmuxRegistryDep = None,
        control_bridge: ControlBridgeDep = None,
    ):
        ...
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

if TYPE_CHECKING:
    from ..core.nats_bridge import NATSControlBridge
    from ..core.sessions.tmux.session_registry import TmuxSessionRegistry
    from .handlers import ControlCommandHandler


# ---------------------------------------------------------------------------
# Dependency getter functions
# ---------------------------------------------------------------------------

def get_tmux_registry(request: Request) -> TmuxSessionRegistry | None:
    """Retrieve the TmuxSessionRegistry from app state (None if unavailable)."""
    return getattr(request.app.state, "tmux_registry", None)


def get_control_bridge(request: Request) -> NATSControlBridge | None:
    """Retrieve the NATSControlBridge from app state (None if unavailable)."""
    return getattr(request.app.state, "control_bridge", None)


def get_control_handler(request: Request) -> ControlCommandHandler | None:
    """Retrieve the ControlCommandHandler from app state (None if unavailable)."""
    return getattr(request.app.state, "control_handler", None)


# ---------------------------------------------------------------------------
# Annotated type aliases for use in route signatures
# ---------------------------------------------------------------------------

TmuxRegistryDep = Annotated["TmuxSessionRegistry | None", Depends(get_tmux_registry)]
ControlBridgeDep = Annotated["NATSControlBridge | None", Depends(get_control_bridge)]
ControlHandlerDep = Annotated["ControlCommandHandler | None", Depends(get_control_handler)]
