"""Layout engine — re-exports from shared core.

Backward-compatible import path:
    from aetherterm.agentserver.core.sessions.tmux.layout_engine import LayoutEngine
"""

from aetherterm.core.pane.layout import LayoutEngine

__all__ = ["LayoutEngine"]
