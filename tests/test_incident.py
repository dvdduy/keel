from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from keel.application.incident.detect import detect_incident
from keel.application.incident.model import Incident, IncidentContext, IncidentStatus
from keel.application.lineage.edges import LineageEdge
from keel.application.lineage.graph import LineageGraph
from keel.application.slo.model import SloEvaluation, SloStatus
from keel.domain.run import Run, RunStatus


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
INCIDENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _evaluation(
    status: SloStatus,
    *,
    attainment: float | None = 0.5,
    error_budget_remaining: float = -1.0,
) -> SloEvaluation:
    return SloEvaluation(
        objective=0.9,
        window_start=NOW - timedelta(days=30),
        window_end=NOW,
        total=10,
        good=5,
        bad=5,
        unknown=0,
        attainment=attainment,
        status=status,
        error_budget_total=1.0,
        error_budget_consumed=5.0,
        error_budget_remaining=error_budget_remaining,
    )


def _run() -> Run:
    return Run(
        id=RUN_ID,
        pipeline_id=PIPELINE_ID,
        created_at=NOW - timedelta(minutes=5),
        status=RunStatus.SUCCESS,
        started_at=NOW - timedelta(minutes=5),
        finished_at=NOW - timedelta(minutes=1),
    )


def _context(
    *,
    subject: str = "raw.orders",
    run: Run | None = None,
    graph: LineageGraph | None = None,
) -> IncidentContext:
    if graph is None:
        graph = LineageGraph.from_edges([])

    return IncidentContext(
        subject=subject,
        pipeline_id=PIPELINE_ID,
        team="revenue",
        owner="data-oncall@example.com",
        run=run,
        graph=graph,
    )


def _detect(
    *,
    evaluation: SloEvaluation | None = None,
    context: IncidentContext | None = None,
) -> Incident | None:
    if evaluation is None:
        evaluation = _evaluation(SloStatus.BREACHING)
    if context is None:
        context = _context()

    return detect_incident(
        slo_name="freshness",
        evaluation=evaluation,
        context=context,
        now=NOW,
        new_id=INCIDENT_ID,
    )


def test_breaching_evaluation_opens_incident() -> None:
    incident = _detect(evaluation=_evaluation(SloStatus.BREACHING))

    assert incident is not None
    assert incident.status is IncidentStatus.OPEN
    assert incident.subject == "raw.orders"
    assert incident.pipeline_id == PIPELINE_ID
    assert incident.slo_name == "freshness"
    assert incident.opened_at == NOW


def test_meeting_evaluation_opens_no_incident() -> None:
    incident = _detect(evaluation=_evaluation(SloStatus.MEETING, attainment=1.0))

    assert incident is None


def test_no_data_evaluation_opens_no_incident() -> None:
    incident = _detect(evaluation=_evaluation(SloStatus.NO_DATA, attainment=None))

    assert incident is None


def test_incident_carries_the_breaching_evaluation() -> None:
    evaluation = _evaluation(
        SloStatus.BREACHING,
        attainment=0.4,
        error_budget_remaining=-4.0,
    )

    incident = _detect(evaluation=evaluation)

    assert incident is not None
    assert incident.evaluation == evaluation
    assert incident.evaluation.attainment == 0.4
    assert incident.evaluation.error_budget_total == 1.0
    assert incident.evaluation.error_budget_consumed == 5.0
    assert incident.evaluation.error_budget_remaining == -4.0


def test_incident_enriched_with_downstream_impact() -> None:
    graph = LineageGraph.from_edges(
        [
            LineageEdge("raw.orders", "stg.orders"),
            LineageEdge("raw.orders", "stg.order_items"),
            LineageEdge("stg.orders", "mart.customer_orders"),
            LineageEdge("stg.order_items", "mart.customer_orders"),
        ]
    )

    incident = _detect(context=_context(graph=graph))

    assert incident is not None
    assert incident.impacted == frozenset({"stg.orders", "stg.order_items", "mart.customer_orders"})
    assert "raw.orders" not in incident.impacted


def test_incident_impact_empty_for_leaf_subject() -> None:
    graph = LineageGraph.from_edges([LineageEdge("raw.orders", "stg.orders")])

    incident = _detect(context=_context(subject="stg.orders", graph=graph))

    assert incident is not None
    assert incident.impacted == frozenset()


def test_incident_captures_run_context() -> None:
    incident = _detect(context=_context(run=_run()))

    assert incident is not None
    assert incident.run_id == RUN_ID


def test_incident_run_context_optional() -> None:
    incident = _detect(context=_context(run=None))

    assert incident is not None
    assert incident.run_id is None


def test_incident_captures_owner_and_team() -> None:
    incident = _detect()

    assert incident is not None
    assert incident.team == "revenue"
    assert incident.owner == "data-oncall@example.com"


def test_incident_id_is_surrogate() -> None:
    incident = _detect()

    assert incident is not None
    assert incident.id == INCIDENT_ID


def test_incident_impact_is_a_snapshot() -> None:
    original_graph = LineageGraph.from_edges([LineageEdge("raw.orders", "stg.orders")])

    incident = _detect(context=_context(graph=original_graph))
    changed_graph = LineageGraph.from_edges(
        [
            LineageEdge("raw.orders", "stg.orders"),
            LineageEdge("stg.orders", "mart.customer_orders"),
        ]
    )

    assert incident is not None
    assert changed_graph.impacted_by("raw.orders") == frozenset(
        {"stg.orders", "mart.customer_orders"}
    )
    assert incident.impacted == frozenset({"stg.orders"})
