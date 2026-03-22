"""Layout engine for pane arrangement.

Server-authoritative: clients request operations, server computes and broadcasts.
Operates on a binary tree of LayoutNode. Service-agnostic.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .models import LayoutNode, LayoutType

log = logging.getLogger("aetherterm.core.pane.layout")


class LayoutEngine:
    """Computes and manipulates a binary-tree layout of panes."""

    @staticmethod
    def split(
        root: LayoutNode,
        target_pane_id: str,
        new_pane_id: str,
        direction: str = "v",
        ratio: float = 0.5,
    ) -> LayoutNode:
        """Split a pane into two.

        Args:
            root: Root layout node.
            target_pane_id: Pane to split.
            new_pane_id: ID for the new pane.
            direction: 'v' for vertical (side by side), 'h' for horizontal (top/bottom).
            ratio: Split ratio (0.0-1.0), how much space the first pane gets.
        """
        split_type = LayoutType.VSPLIT if direction == "v" else LayoutType.HSPLIT

        def _split_node(node: LayoutNode) -> LayoutNode:
            if node.type == LayoutType.LEAF and node.pane_id == target_pane_id:
                return LayoutNode(
                    type=split_type,
                    children=[
                        LayoutNode(type=LayoutType.LEAF, pane_id=target_pane_id),
                        LayoutNode(type=LayoutType.LEAF, pane_id=new_pane_id),
                    ],
                    ratio=ratio,
                )
            if node.children:
                node.children = [_split_node(c) for c in node.children]
            return node

        return _split_node(root)

    @staticmethod
    def remove(root: LayoutNode, pane_id: str) -> Optional[LayoutNode]:
        """Remove a pane from the layout.

        Returns updated root node, or None if the layout is now empty.
        """

        def _remove_node(node: LayoutNode) -> Optional[LayoutNode]:
            if node.type == LayoutType.LEAF:
                return None if node.pane_id == pane_id else node

            new_children = []
            for child in node.children:
                result = _remove_node(child)
                if result is not None:
                    new_children.append(result)

            if not new_children:
                return None
            if len(new_children) == 1:
                return new_children[0]
            node.children = new_children
            return node

        return _remove_node(root)

    @staticmethod
    def resize(root: LayoutNode, pane_id: str, delta: float) -> LayoutNode:
        """Adjust the split ratio of the parent containing the given pane."""
        parent = root.find_parent(pane_id)
        if parent is not None:
            new_ratio = max(0.1, min(0.9, parent.ratio + delta))
            parent.ratio = new_ratio
        return root

    @staticmethod
    def swap(root: LayoutNode, pane_a: str, pane_b: str) -> LayoutNode:
        """Swap the positions of two panes in the layout."""
        leaf_a = root.find_leaf(pane_a)
        leaf_b = root.find_leaf(pane_b)
        if leaf_a is not None and leaf_b is not None:
            leaf_a.pane_id, leaf_b.pane_id = leaf_b.pane_id, leaf_a.pane_id
        return root

    @staticmethod
    def get_pane_order(root: LayoutNode) -> List[str]:
        """Get pane IDs in visual order (left-to-right, top-to-bottom)."""
        return root.collect_pane_ids()

    @staticmethod
    def next_pane(root: LayoutNode, current_pane_id: str) -> Optional[str]:
        """Get the next pane in visual order (cyclic)."""
        order = root.collect_pane_ids()
        if not order or current_pane_id not in order:
            return None
        idx = order.index(current_pane_id)
        return order[(idx + 1) % len(order)]

    @staticmethod
    def prev_pane(root: LayoutNode, current_pane_id: str) -> Optional[str]:
        """Get the previous pane in visual order (cyclic)."""
        order = root.collect_pane_ids()
        if not order or current_pane_id not in order:
            return None
        idx = order.index(current_pane_id)
        return order[(idx - 1) % len(order)]

    @staticmethod
    def adjacent_pane(
        root: LayoutNode,
        current_pane_id: str,
        direction: str,
    ) -> Optional[str]:
        """Find adjacent pane in a given direction ('up', 'down', 'left', 'right')."""
        if direction in ("left", "up"):
            return LayoutEngine.prev_pane(root, current_pane_id)
        return LayoutEngine.next_pane(root, current_pane_id)

    @staticmethod
    def compute_rects(
        root: LayoutNode,
        x: float = 0,
        y: float = 0,
        width: float = 1.0,
        height: float = 1.0,
    ) -> Dict[str, Tuple[float, float, float, float]]:
        """Compute normalized rectangles (0-1) for each pane.

        Returns dict mapping pane_id to (x, y, width, height).
        """
        rects: Dict[str, Tuple[float, float, float, float]] = {}

        if root.type == LayoutType.LEAF and root.pane_id:
            rects[root.pane_id] = (x, y, width, height)
        elif root.type == LayoutType.VSPLIT and len(root.children) == 2:
            left_w = width * root.ratio
            right_w = width - left_w
            rects.update(LayoutEngine.compute_rects(root.children[0], x, y, left_w, height))
            rects.update(
                LayoutEngine.compute_rects(root.children[1], x + left_w, y, right_w, height)
            )
        elif root.type == LayoutType.HSPLIT and len(root.children) == 2:
            top_h = height * root.ratio
            bottom_h = height - top_h
            rects.update(LayoutEngine.compute_rects(root.children[0], x, y, width, top_h))
            rects.update(
                LayoutEngine.compute_rects(root.children[1], x, y + top_h, width, bottom_h)
            )

        return rects

    @staticmethod
    def build_balanced(pane_ids: List[str], direction: str = "hsplit") -> LayoutNode:
        """Build a balanced binary tree layout from a list of pane IDs.

        Alternates between hsplit and vsplit at each depth level.
        """
        if not pane_ids:
            return LayoutNode(type=LayoutType.LEAF)
        if len(pane_ids) == 1:
            return LayoutNode(type=LayoutType.LEAF, pane_id=pane_ids[0])

        mid = len(pane_ids) // 2
        layout_type = LayoutType.HSPLIT if direction == "hsplit" else LayoutType.VSPLIT
        next_dir = "vsplit" if direction == "hsplit" else "hsplit"
        return LayoutNode(
            type=layout_type,
            children=[
                LayoutEngine.build_balanced(pane_ids[:mid], next_dir),
                LayoutEngine.build_balanced(pane_ids[mid:], next_dir),
            ],
        )
