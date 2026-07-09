from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from keel.application.incident.group import IncidentGroup, group_incidents
from keel.application.incident.model import Incident, IncidentStatus
from keel.application.lineage.edges import LineageEdge
from keel.application.lineage.graph import LineageGraph
from keel.application.slo.model import SloEvaluation, SloStatus


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _evaluation() -> SloEvaluation:
    return SloEvaluation(
        objective=0.9,
        window_start=NOW - timedelta(days=30),
        window_end=NOW,
        total=10,
        good=5,
        bad=5,
        unknown=0,
        attainment=0.5,
        status=SloStatus.BREACHING,
        error_budget_total=1.0,
        error_budget_consumed=5.0,
        error_budget_remaining=-1.0,
    )


def _incident(
    subject: str,
    *,
    slo_name: str = "freshness",
    index: int = 1,
) -> Incident:
    return Incident(
        id=UUID(int=index),
        subject=subject,
        pipeline_id=PIPELINE_ID,
        slo_name=slo_name,
        status=IncidentStatus.OPEN,
        evaluation=_evaluation(),
        run_id=None,
        team="revenue",
        owner="data-oncall@example.com",
        impacted=frozenset(),
        opened_at=NOW,
    )


def _graph(*edges: tuple[str, str]) -> LineageGraph:
    return LineageGraph.from_edges(
        LineageEdge(upstream, downstream) for upstream, downstream in edges
    )


def _members(group: IncidentGroup) -> tuple[Incident, ...]:
    return group.roots + group.correlated


def test_single_isolated_breach_is_its_own_group() -> None:
    incident = _incident("raw.orders")

    groups = group_incidents([incident], _graph())

    assert groups == (IncidentGroup(roots=(incident,), correlated=()),)


def test_independent_breaches_stay_separate() -> None:
    raw_orders = _incident("raw.orders", index=1)
    raw_customers = _incident("raw.customers", index=2)

    groups = group_incidents([raw_customers, raw_orders], _graph())

    assert groups == (
        IncidentGroup(roots=(raw_customers,), correlated=()),
        IncidentGroup(roots=(raw_orders,), correlated=()),
    )


def test_downstream_breach_groups_under_upstream_root() -> None:
    raw_orders = _incident("raw.orders", index=1)
    stg_orders = _incident("stg.orders", index=2)

    groups = group_incidents(
        [stg_orders, raw_orders],
        _graph(("raw.orders", "stg.orders")),
    )

    assert groups == (IncidentGroup(roots=(raw_orders,), correlated=(stg_orders,)),)


def test_fan_out_of_twenty_collapses_to_one_group() -> None:
    root = _incident("raw.orders", index=1)
    downstream = tuple(
        _incident(f"mart.orders_{number:02}", index=number + 1) for number in range(1, 21)
    )
    graph = _graph(*(("raw.orders", incident.subject) for incident in downstream))

    groups = group_incidents([*downstream, root], graph)

    assert len(groups) == 1
    assert groups[0].roots == (root,)
    assert groups[0].correlated == downstream


def test_root_is_the_upstream_incident() -> None:
    raw_orders = _incident("raw.orders", index=1)
    stg_orders = _incident("stg.orders", index=2)
    mart_orders = _incident("mart.orders", index=3)

    groups = group_incidents(
        [mart_orders, stg_orders, raw_orders],
        _graph(("raw.orders", "stg.orders"), ("stg.orders", "mart.orders")),
    )

    assert groups[0].roots == (raw_orders,)


def test_correlated_holds_only_downstream_incidents() -> None:
    raw_orders = _incident("raw.orders", index=1)
    stg_orders = _incident("stg.orders", index=2)
    mart_orders = _incident("mart.orders", index=3)

    groups = group_incidents(
        [raw_orders, mart_orders, stg_orders],
        _graph(("raw.orders", "stg.orders"), ("stg.orders", "mart.orders")),
    )

    assert groups[0].correlated == (mart_orders, stg_orders)


def test_intermediate_non_breaching_node_still_groups_endpoints() -> None:
    raw_orders = _incident("raw.orders", index=1)
    mart_orders = _incident("mart.orders", index=2)

    groups = group_incidents(
        [mart_orders, raw_orders],
        _graph(("raw.orders", "stg.orders"), ("stg.orders", "mart.orders")),
    )

    assert groups == (IncidentGroup(roots=(raw_orders,), correlated=(mart_orders,)),)


def test_grouping_is_a_partition() -> None:
    incidents = (
        _incident("raw.orders", index=1),
        _incident("stg.orders", index=2),
        _incident("raw.customers", index=3),
        _incident("mart.customers", index=4),
    )

    groups = group_incidents(
        incidents,
        _graph(
            ("raw.orders", "stg.orders"),
            ("raw.customers", "stg.customers"),
            ("stg.customers", "mart.customers"),
        ),
    )
    grouped = tuple(incident for group in groups for incident in _members(group))

    assert len(grouped) == len(incidents)
    assert frozenset(grouped) == frozenset(incidents)


def test_empty_input_yields_no_groups() -> None:
    assert group_incidents([], _graph()) == ()


def test_diamond_lineage_forms_one_group() -> None:
    incidents = (
        _incident("raw.orders", index=1),
        _incident("stg.orders", index=2),
        _incident("stg.order_items", index=3),
        _incident("mart.customer_orders", index=4),
    )

    groups = group_incidents(
        incidents,
        _graph(
            ("raw.orders", "stg.orders"),
            ("raw.orders", "stg.order_items"),
            ("stg.orders", "mart.customer_orders"),
            ("stg.order_items", "mart.customer_orders"),
        ),
    )

    assert len(groups) == 1
    assert groups == (
        IncidentGroup(
            roots=(incidents[0],),
            correlated=(incidents[3], incidents[2], incidents[1]),
        ),
    )


def test_two_independent_roots_reaching_shared_downstream_form_one_group() -> None:
    raw_orders = _incident("raw.orders", index=1)
    raw_payments = _incident("raw.payments", index=2)
    mart_revenue = _incident("mart.revenue", index=3)

    groups = group_incidents(
        [mart_revenue, raw_payments, raw_orders],
        _graph(("raw.orders", "mart.revenue"), ("raw.payments", "mart.revenue")),
    )

    assert groups == (IncidentGroup(roots=(raw_orders, raw_payments), correlated=(mart_revenue,)),)


def test_same_subject_two_slos_share_a_group() -> None:
    freshness = _incident("raw.orders", slo_name="freshness", index=1)
    quality = _incident("raw.orders", slo_name="quality", index=2)

    groups = group_incidents([quality, freshness], _graph())

    assert groups == (IncidentGroup(roots=(freshness, quality), correlated=()),)


def test_output_is_deterministic() -> None:
    raw_orders = _incident("raw.orders", slo_name="freshness", index=1)
    raw_orders_quality = _incident("raw.orders", slo_name="quality", index=2)
    stg_orders = _incident("stg.orders", slo_name="freshness", index=3)
    raw_customers = _incident("raw.customers", slo_name="freshness", index=4)

    groups = group_incidents(
        [stg_orders, raw_orders_quality, raw_customers, raw_orders],
        _graph(("raw.orders", "stg.orders")),
    )

    assert groups == (
        IncidentGroup(roots=(raw_customers,), correlated=()),
        IncidentGroup(roots=(raw_orders, raw_orders_quality), correlated=(stg_orders,)),
    )
