from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from keel.application.specs.models import PipelineSpec
from keel.application.specs.versioning import SpecVersion

if TYPE_CHECKING:
    from keel.application.lineage.graph import LineageGraph


@dataclass(frozen=True)
class LineageEdge:
    upstream: str
    downstream: str


def declared_edges(spec: PipelineSpec) -> frozenset[LineageEdge]:
    """Return table-level lineage declared by one pipeline spec.

    The spec is producer intent. Runtime artifacts such as the dbt manifest
    verify these edges separately; they do not define them.
    """

    source = f"source:{spec.source.type.value}:{spec.source.path}"
    edges = {LineageEdge(upstream=source, downstream=spec.destination)}

    if spec.transform is not None:
        edges.add(
            LineageEdge(
                upstream=spec.destination,
                downstream=f"main.{spec.transform}",
            )
        )

    return frozenset(edges)


def edges_for_version(version: SpecVersion) -> frozenset[LineageEdge]:
    """Project declared lineage from an authoritative spec version."""

    spec = PipelineSpec.model_validate_json(version.content)
    return declared_edges(spec)


def build_lineage_graph(versions: Iterable[SpecVersion]) -> LineageGraph:
    """Build a platform graph from authoritative spec versions."""

    from keel.application.lineage.graph import LineageGraph

    edges = (edge for version in versions for edge in edges_for_version(version))
    return LineageGraph.from_edges(edges)
