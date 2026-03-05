"""Preset layouts for tmux-style pane arrangement."""

from __future__ import annotations

from typing import List

from .models import LayoutNode, LayoutType


def even_horizontal(pane_ids: List[str]) -> LayoutNode:
    """All panes side by side, equal width."""
    if not pane_ids:
        return LayoutNode(type=LayoutType.LEAF)
    if len(pane_ids) == 1:
        return LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0])

    # Build right-leaning chain
    node = LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[-1])
    for i in range(len(pane_ids) - 2, -1, -1):
        ratio = 1.0 / (len(pane_ids) - i)
        node = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[i]),
                node,
            ],
            ratio=ratio,
        )
    return node


def even_vertical(pane_ids: List[str]) -> LayoutNode:
    """All panes stacked vertically, equal height."""
    if not pane_ids:
        return LayoutNode(type=LayoutType.LEAF)
    if len(pane_ids) == 1:
        return LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0])

    node = LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[-1])
    for i in range(len(pane_ids) - 2, -1, -1):
        ratio = 1.0 / (len(pane_ids) - i)
        node = LayoutNode(
            type=LayoutType.HSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[i]),
                node,
            ],
            ratio=ratio,
        )
    return node


def main_horizontal(pane_ids: List[str]) -> LayoutNode:
    """First pane on top (large), remaining panes on bottom (equal width)."""
    if len(pane_ids) <= 1:
        return even_horizontal(pane_ids)

    bottom = even_horizontal(pane_ids[1:])
    return LayoutNode(
        type=LayoutType.HSPLIT,
        children=[
            LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0]),
            bottom,
        ],
        ratio=0.6,
    )


def main_vertical(pane_ids: List[str]) -> LayoutNode:
    """First pane on left (large), remaining panes on right (equal height)."""
    if len(pane_ids) <= 1:
        return even_vertical(pane_ids)

    right = even_vertical(pane_ids[1:])
    return LayoutNode(
        type=LayoutType.VSPLIT,
        children=[
            LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0]),
            right,
        ],
        ratio=0.6,
    )


def tiled(pane_ids: List[str]) -> LayoutNode:
    """Grid layout: balanced 2x2 style tiling."""
    n = len(pane_ids)
    if n <= 1:
        return even_horizontal(pane_ids)
    if n == 2:
        return even_horizontal(pane_ids)
    if n == 3:
        return LayoutNode(
            type=LayoutType.HSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0]),
                even_horizontal(pane_ids[1:]),
            ],
            ratio=0.5,
        )
    # 4+: split into two rows
    mid = n // 2
    return LayoutNode(
        type=LayoutType.HSPLIT,
        children=[
            even_horizontal(pane_ids[:mid]),
            even_horizontal(pane_ids[mid:]),
        ],
        ratio=0.5,
    )


PRESET_LAYOUTS = {
    "even-horizontal": even_horizontal,
    "even-vertical": even_vertical,
    "main-horizontal": main_horizontal,
    "main-vertical": main_vertical,
    "tiled": tiled,
}
