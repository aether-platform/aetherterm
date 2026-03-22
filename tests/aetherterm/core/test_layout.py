"""Tests for core/pane/layout — LayoutEngine and LayoutNode."""

import pytest

from aetherterm.core.pane.layout import LayoutEngine
from aetherterm.core.pane.models import LayoutNode, LayoutType


class TestLayoutNode:
    def test_leaf_to_dict(self):
        node = LayoutNode(type=LayoutType.LEAF, pane_id="p1")
        d = node.to_dict()
        assert d["type"] == "leaf"
        assert d["pane_id"] == "p1"

    def test_split_to_dict(self):
        node = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
            ratio=0.6,
        )
        d = node.to_dict()
        assert d["type"] == "vsplit"
        assert d["ratio"] == 0.6
        assert len(d["children"]) == 2

    def test_from_dict_roundtrip(self):
        original = LayoutNode(
            type=LayoutType.HSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="x"),
                LayoutNode(
                    type=LayoutType.VSPLIT,
                    children=[
                        LayoutNode(type=LayoutType.LEAF, pane_id="y"),
                        LayoutNode(type=LayoutType.LEAF, pane_id="z"),
                    ],
                ),
            ],
        )
        rebuilt = LayoutNode.from_dict(original.to_dict())
        assert rebuilt.collect_pane_ids() == ["x", "y", "z"]
        assert rebuilt.type == LayoutType.HSPLIT

    def test_find_leaf(self):
        node = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        assert node.find_leaf("b").pane_id == "b"
        assert node.find_leaf("c") is None

    def test_find_parent(self):
        node = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        parent = node.find_parent("b")
        assert parent is node

    def test_collect_pane_ids_empty(self):
        node = LayoutNode(type=LayoutType.LEAF)
        assert node.collect_pane_ids() == []


class TestLayoutEngineSplit:
    def test_split_leaf(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="p1")
        result = LayoutEngine.split(root, "p1", "p2", direction="v")
        assert result.type == LayoutType.VSPLIT
        assert result.children[0].pane_id == "p1"
        assert result.children[1].pane_id == "p2"

    def test_split_horizontal(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="p1")
        result = LayoutEngine.split(root, "p1", "p2", direction="h")
        assert result.type == LayoutType.HSPLIT

    def test_split_nested(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="a")
        root = LayoutEngine.split(root, "a", "b", "v")
        root = LayoutEngine.split(root, "b", "c", "h")
        ids = root.collect_pane_ids()
        assert set(ids) == {"a", "b", "c"}

    def test_split_with_ratio(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="p1")
        result = LayoutEngine.split(root, "p1", "p2", ratio=0.7)
        assert result.ratio == 0.7

    def test_split_nonexistent_target(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="p1")
        result = LayoutEngine.split(root, "missing", "p2")
        # Should return unchanged
        assert result.type == LayoutType.LEAF
        assert result.pane_id == "p1"


class TestLayoutEngineRemove:
    def test_remove_from_split(self):
        root = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        result = LayoutEngine.remove(root, "a")
        assert result.type == LayoutType.LEAF
        assert result.pane_id == "b"

    def test_remove_last(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="only")
        result = LayoutEngine.remove(root, "only")
        assert result is None

    def test_remove_nonexistent(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="a")
        result = LayoutEngine.remove(root, "missing")
        assert result.pane_id == "a"


class TestLayoutEngineResize:
    def test_resize(self):
        root = LayoutNode(
            type=LayoutType.VSPLIT,
            ratio=0.5,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        LayoutEngine.resize(root, "a", 0.2)
        assert root.ratio == pytest.approx(0.7)

    def test_resize_clamps(self):
        root = LayoutNode(
            type=LayoutType.VSPLIT,
            ratio=0.5,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        LayoutEngine.resize(root, "a", 10.0)  # Way over
        assert root.ratio == pytest.approx(0.9)

        LayoutEngine.resize(root, "a", -10.0)  # Way under
        assert root.ratio == pytest.approx(0.1)


class TestLayoutEngineSwap:
    def test_swap(self):
        root = LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        LayoutEngine.swap(root, "a", "b")
        assert root.children[0].pane_id == "b"
        assert root.children[1].pane_id == "a"


class TestLayoutEngineNavigation:
    def _make_tree(self):
        return LayoutNode(
            type=LayoutType.VSPLIT,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(
                    type=LayoutType.HSPLIT,
                    children=[
                        LayoutNode(type=LayoutType.LEAF, pane_id="b"),
                        LayoutNode(type=LayoutType.LEAF, pane_id="c"),
                    ],
                ),
            ],
        )

    def test_get_pane_order(self):
        assert LayoutEngine.get_pane_order(self._make_tree()) == ["a", "b", "c"]

    def test_next_pane(self):
        root = self._make_tree()
        assert LayoutEngine.next_pane(root, "a") == "b"
        assert LayoutEngine.next_pane(root, "c") == "a"  # cyclic

    def test_prev_pane(self):
        root = self._make_tree()
        assert LayoutEngine.prev_pane(root, "a") == "c"  # cyclic
        assert LayoutEngine.prev_pane(root, "b") == "a"

    def test_nav_nonexistent(self):
        root = self._make_tree()
        assert LayoutEngine.next_pane(root, "missing") is None


class TestLayoutEngineComputeRects:
    def test_single_leaf(self):
        root = LayoutNode(type=LayoutType.LEAF, pane_id="a")
        rects = LayoutEngine.compute_rects(root)
        assert rects["a"] == pytest.approx((0, 0, 1.0, 1.0))

    def test_vsplit(self):
        root = LayoutNode(
            type=LayoutType.VSPLIT,
            ratio=0.5,
            children=[
                LayoutNode(type=LayoutType.LEAF, pane_id="a"),
                LayoutNode(type=LayoutType.LEAF, pane_id="b"),
            ],
        )
        rects = LayoutEngine.compute_rects(root)
        assert rects["a"] == pytest.approx((0, 0, 0.5, 1.0))
        assert rects["b"] == pytest.approx((0.5, 0, 0.5, 1.0))


class TestBuildBalanced:
    def test_empty(self):
        node = LayoutEngine.build_balanced([])
        assert node.type == LayoutType.LEAF
        assert node.pane_id is None

    def test_single(self):
        node = LayoutEngine.build_balanced(["a"])
        assert node.pane_id == "a"

    def test_two(self):
        node = LayoutEngine.build_balanced(["a", "b"])
        assert node.type == LayoutType.HSPLIT
        assert set(node.collect_pane_ids()) == {"a", "b"}

    def test_many_preserves_all_ids(self):
        ids = [f"p{i}" for i in range(7)]
        node = LayoutEngine.build_balanced(ids)
        assert set(node.collect_pane_ids()) == set(ids)

    def test_alternates_direction(self):
        node = LayoutEngine.build_balanced(["a", "b", "c", "d"])
        # Top level should be hsplit (default), children should be vsplit
        assert node.type == LayoutType.HSPLIT
        for child in node.children:
            if child.type != LayoutType.LEAF:
                assert child.type == LayoutType.VSPLIT
