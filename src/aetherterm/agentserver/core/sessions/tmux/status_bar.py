"""Status bar generation for tmux-style display."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .models import TmuxSession


def generate_status(session: TmuxSession) -> Dict[str, Any]:
    """Generate status bar data for a session.

    Returns:
        Dict with left, center, right segments.
    """
    windows: List[Dict[str, Any]] = []
    for wid, win in session.windows.items():
        pane_count = len(win.panes)
        windows.append(
            {
                "window_id": wid,
                "index": win.window_index,
                "name": win.name,
                "pane_count": pane_count,
                "active": wid == session.active_window_id,
            }
        )

    windows.sort(key=lambda w: w["index"])

    active_window = session.windows.get(session.active_window_id)
    active_pane_info = ""
    if active_window:
        active_pane = active_window.panes.get(active_window.active_pane_id)
        if active_pane:
            active_pane_info = f"{active_pane.cols}x{active_pane.rows}"

    return {
        "left": {
            "session_name": session.name,
            "session_id": session.session_id[:12],
        },
        "center": {
            "windows": windows,
        },
        "right": {
            "pane_info": active_pane_info,
            "time": time.strftime("%H:%M"),
        },
    }
