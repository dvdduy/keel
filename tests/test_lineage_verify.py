import pytest

from keel.application.lineage.edges import LineageEdge
from keel.application.lineage.verify import manifest_edges, verify_lineage
from keel.application.ports.transform import ManifestNode, TransformError, TransformManifest


def _node(
    unique_id: str,
    *,
    resource_type: str = "model",
    name: str,
    schema: str,
    relation: str | None = None,
    depends_on: frozenset[str] = frozenset(),
) -> ManifestNode:
    return ManifestNode(
        unique_id=unique_id,
        resource_type=resource_type,
        name=name,
        schema=schema,
        relation=relation or name,
        depends_on=depends_on,
    )


def test_model_source_dependency_projects_to_physical_edge() -> None:
    manifest = TransformManifest(
        nodes=(
            _node(
                "source.keel_transform.raw.orders",
                resource_type="source",
                name="orders",
                schema="raw",
            ),
            _node(
                "model.keel_transform.stg_orders",
                name="stg_orders",
                schema="main",
                depends_on=frozenset({"source.keel_transform.raw.orders"}),
            ),
        )
    )

    assert manifest_edges(manifest) == frozenset({LineageEdge("raw.orders", "main.stg_orders")})


def test_unknown_parent_unique_id_is_rejected() -> None:
    manifest = TransformManifest(
        nodes=(
            _node(
                "model.keel_transform.stg_orders",
                name="stg_orders",
                schema="main",
                depends_on=frozenset({"source.keel_transform.raw.orders"}),
            ),
        )
    )

    with pytest.raises(TransformError):
        manifest_edges(manifest)


def test_declared_edge_present_in_manifest_is_verified() -> None:
    edge = LineageEdge("raw.orders", "main.stg_orders")

    verification = verify_lineage(frozenset({edge}), _manifest_with(edge))

    assert verification.verified == frozenset({edge})
    assert verification.missing == frozenset()
    assert verification.undeclared == frozenset()
    assert verification.ok is True


def test_declared_edge_absent_from_manifest_is_missing() -> None:
    edge = LineageEdge("raw.orders", "main.stg_orders")

    verification = verify_lineage(frozenset({edge}), TransformManifest(nodes=()))

    assert verification.verified == frozenset()
    assert verification.missing == frozenset({edge})
    assert verification.undeclared == frozenset()
    assert verification.ok is False


def test_csv_ingestion_edge_is_out_of_scope_not_missing() -> None:
    ingestion = LineageEdge("source:csv:feeds/orders.csv", "raw.orders")

    verification = verify_lineage(frozenset({ingestion}), TransformManifest(nodes=()))

    assert verification.out_of_scope == frozenset({ingestion})
    assert verification.missing == frozenset()
    assert verification.ok is True


def test_manifest_edge_outside_governed_frontier_is_ignored() -> None:
    declared = LineageEdge("raw.orders", "main.stg_orders")
    unrelated = LineageEdge("main.stg_orders", "main.mart_customer_orders")
    manifest = _manifest_with(declared, unrelated)

    verification = verify_lineage(frozenset({declared}), manifest)

    assert verification.verified == frozenset({declared})
    assert verification.undeclared == frozenset()


def test_swapped_source_reports_both_missing_and_undeclared() -> None:
    declared = LineageEdge("raw.orders", "main.stg_orders")
    observed = LineageEdge("raw.order_events", "main.stg_orders")

    verification = verify_lineage(frozenset({declared}), _manifest_with(observed))

    assert verification.verified == frozenset()
    assert verification.missing == frozenset({declared})
    assert verification.undeclared == frozenset({observed})
    assert verification.ok is False


def test_ok_true_only_when_no_missing_and_no_undeclared() -> None:
    declared = LineageEdge("raw.orders", "main.stg_orders")

    assert verify_lineage(frozenset({declared}), _manifest_with(declared)).ok is True
    assert verify_lineage(frozenset({declared}), TransformManifest(nodes=())).ok is False
    assert (
        verify_lineage(
            frozenset({declared}),
            _manifest_with(LineageEdge("raw.order_events", "main.stg_orders")),
        ).ok
        is False
    )


def _manifest_with(*edges: LineageEdge) -> TransformManifest:
    nodes_by_identity: dict[str, ManifestNode] = {}

    for edge in edges:
        upstream = nodes_by_identity.setdefault(
            edge.upstream,
            _node_for_identity(edge.upstream),
        )
        downstream = nodes_by_identity.get(edge.downstream)
        if downstream is None:
            downstream = _node_for_identity(edge.downstream)

        nodes_by_identity[edge.downstream] = ManifestNode(
            unique_id=downstream.unique_id,
            resource_type=downstream.resource_type,
            name=downstream.name,
            schema=downstream.schema,
            relation=downstream.relation,
            depends_on=downstream.depends_on | frozenset({upstream.unique_id}),
        )

    return TransformManifest(nodes=tuple(nodes_by_identity.values()))


def _node_for_identity(identity: str) -> ManifestNode:
    schema, relation = identity.split(".", maxsplit=1)
    return _node(
        f"model.keel_transform.{relation}",
        name=relation,
        schema=schema,
        relation=relation,
    )
