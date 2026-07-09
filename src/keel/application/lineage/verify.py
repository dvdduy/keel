from __future__ import annotations

from dataclasses import dataclass

from keel.application.lineage.edges import LineageEdge
from keel.application.ports.transform import TransformError, TransformManifest


def manifest_edges(manifest: TransformManifest) -> frozenset[LineageEdge]:
    """Project the dbt dependency graph into Keel schema.table vocabulary.

    For each node's depends_on parent, resolve both endpoints to their
    physical_identity and emit LineageEdge(parent, child).
    """

    nodes_by_id = {node.unique_id: node for node in manifest.nodes}
    edges: set[LineageEdge] = set()

    for child in manifest.nodes:
        for parent_id in child.depends_on:
            parent = nodes_by_id.get(parent_id)
            if parent is None:
                raise TransformError(
                    "manifest dependency references unknown unique_id " f"{parent_id!r}"
                )

            edges.add(
                LineageEdge(
                    upstream=parent.physical_identity,
                    downstream=child.physical_identity,
                )
            )

    return frozenset(edges)


@dataclass(frozen=True)
class LineageVerification:
    verified: frozenset[LineageEdge]
    missing: frozenset[LineageEdge]
    undeclared: frozenset[LineageEdge]
    out_of_scope: frozenset[LineageEdge]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.undeclared


def verify_lineage(
    declared: frozenset[LineageEdge],
    manifest: TransformManifest,
) -> LineageVerification:
    out_of_scope = frozenset(edge for edge in declared if edge.upstream.startswith("source:"))
    in_scope = declared - out_of_scope
    governed = frozenset(node for edge in in_scope for node in (edge.upstream, edge.downstream))
    relevant_observed = frozenset(
        edge for edge in manifest_edges(manifest) if edge.downstream in governed
    )

    return LineageVerification(
        verified=in_scope & relevant_observed,
        missing=in_scope - relevant_observed,
        undeclared=relevant_observed - in_scope,
        out_of_scope=out_of_scope,
    )
