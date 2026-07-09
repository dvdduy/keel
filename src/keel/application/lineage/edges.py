from __future__ import annotations

from dataclasses import dataclass

from keel.application.specs.models import PipelineSpec
from keel.application.specs.versioning import SpecVersion


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
