from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from keel.application.lineage.edges import LineageEdge


@dataclass(frozen=True)
class LineageGraph:
    _downstream: Mapping[str, frozenset[str]]
    _upstream: Mapping[str, frozenset[str]]

    @classmethod
    def from_edges(cls, edges: Iterable[LineageEdge]) -> "LineageGraph":
        downstream: dict[str, set[str]] = {}
        upstream: dict[str, set[str]] = {}

        for edge in set(edges):
            downstream.setdefault(edge.upstream, set()).add(edge.downstream)
            upstream.setdefault(edge.downstream, set()).add(edge.upstream)
            downstream.setdefault(edge.downstream, set())
            upstream.setdefault(edge.upstream, set())

        return cls(
            _downstream={node: frozenset(neighbors) for node, neighbors in downstream.items()},
            _upstream={node: frozenset(neighbors) for node, neighbors in upstream.items()},
        )

    def impacted_by(self, node: str) -> frozenset[str]:
        """Transitive downstream closure of `node`. Origin excluded."""

        return self._reachable_from(node, self._downstream)

    def feeds(self, node: str) -> frozenset[str]:
        """Transitive upstream closure of `node`. Origin excluded. (Symmetric.)"""

        return self._reachable_from(node, self._upstream)

    def contains(self, node: str) -> bool:
        return node in self._downstream or node in self._upstream

    @staticmethod
    def _reachable_from(node: str, adjacency: Mapping[str, frozenset[str]]) -> frozenset[str]:
        visited = {node}
        reached: set[str] = set()
        frontier = deque(adjacency.get(node, frozenset()))

        while frontier:
            current = frontier.popleft()
            if current in visited:
                continue

            visited.add(current)
            reached.add(current)
            frontier.extend(adjacency.get(current, frozenset()))

        return frozenset(reached)
