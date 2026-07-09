from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from keel.application.lineage.edges import LineageEdge, declared_edges, edges_for_version
from keel.application.specs.models import (
    ColumnType,
    ContractColumn,
    FreshnessSpec,
    PipelineSpec,
    SourceSpec,
    SourceType,
)
from keel.application.specs.versioning import SpecVersion, canonical_spec_json, spec_content_hash


def _spec(*, transform: str | None = None) -> PipelineSpec:
    return PipelineSpec(
        name="orders_daily",
        team="analytics",
        owner="alice@example.com",
        source=SourceSpec(type=SourceType.CSV, path="feeds/orders.csv"),
        destination="raw.orders",
        contract=(ContractColumn(name="order_id", type=ColumnType.INTEGER),),
        transform=transform,
        freshness=FreshnessSpec(max_age_minutes=60),
    )


def test_no_transform_declares_single_source_to_destination_edge() -> None:
    assert declared_edges(_spec()) == frozenset(
        {LineageEdge(upstream="source:csv:feeds/orders.csv", downstream="raw.orders")}
    )


def test_transform_declares_source_to_raw_then_raw_to_final_edges() -> None:
    assert declared_edges(_spec(transform="mart_orders")) == frozenset(
        {
            LineageEdge(upstream="source:csv:feeds/orders.csv", downstream="raw.orders"),
            LineageEdge(upstream="raw.orders", downstream="main.mart_orders"),
        }
    )


def test_external_source_node_is_distinguishable_from_datasets() -> None:
    (edge,) = declared_edges(_spec())

    assert edge.upstream.startswith("source:csv:")
    assert edge.upstream != "feeds.orders"


def test_declared_edges_are_a_deduplicated_frozenset() -> None:
    edges = declared_edges(_spec(transform="mart_orders"))

    assert isinstance(edges, frozenset)
    assert len(edges | edges) == 2


def test_declared_edges_are_order_independent_and_hashable() -> None:
    source_to_raw = LineageEdge("source:csv:feeds/orders.csv", "raw.orders")
    raw_to_final = LineageEdge("raw.orders", "main.mart_orders")

    assert frozenset((source_to_raw, raw_to_final)) == frozenset((raw_to_final, source_to_raw))
    assert {source_to_raw: "declared"}[source_to_raw] == "declared"


def test_edges_for_version_validates_content_and_delegates_to_declared_edges() -> None:
    spec = _spec(transform="mart_orders")
    version = SpecVersion(
        version_id=uuid4(),
        pipeline_id=uuid4(),
        spec_id=spec_content_hash(spec),
        parent_id=None,
        content=canonical_spec_json(spec),
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
    )

    assert edges_for_version(version) == declared_edges(spec)
    assert edges_for_version(replace(version, content=version.content)) == declared_edges(spec)
