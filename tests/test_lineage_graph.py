from __future__ import annotations

from keel.application.lineage.edges import LineageEdge
from keel.application.lineage.graph import LineageGraph


def test_impacted_by_returns_empty_for_unknown_node() -> None:
    graph = LineageGraph.from_edges([LineageEdge("a", "b")])

    assert graph.impacted_by("missing") == frozenset()


def test_impacted_by_returns_direct_downstream_neighbors() -> None:
    graph = LineageGraph.from_edges([LineageEdge("a", "b")])

    assert graph.impacted_by("a") == frozenset({"b"})


def test_impacted_by_is_transitive_across_multiple_hops() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("a", "b"),
            LineageEdge("b", "c"),
        ]
    )

    assert graph.impacted_by("a") == frozenset({"b", "c"})


def test_impacted_by_excludes_the_origin_node() -> None:
    graph = LineageGraph.from_edges([LineageEdge("a", "a")])

    assert graph.impacted_by("a") == frozenset()


def test_impacted_by_terminates_and_excludes_origin_on_a_cycle() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("a", "b"),
            LineageEdge("b", "a"),
        ]
    )

    assert graph.impacted_by("a") == frozenset({"b"})


def test_impacted_by_dedupes_on_diamond_fan_out() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("a", "b"),
            LineageEdge("a", "c"),
            LineageEdge("b", "d"),
            LineageEdge("c", "d"),
        ]
    )

    assert graph.impacted_by("a") == frozenset({"b", "c", "d"})


def test_feeds_returns_transitive_upstream() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("a", "b"),
            LineageEdge("b", "c"),
        ]
    )

    assert graph.feeds("c") == frozenset({"a", "b"})


def test_from_edges_deduplicates_repeated_edges() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("a", "b"),
            LineageEdge("a", "b"),
            LineageEdge("b", "c"),
        ]
    )

    assert graph.impacted_by("a") == frozenset({"b", "c"})
