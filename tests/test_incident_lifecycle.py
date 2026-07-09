from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from keel.application.incident.lifecycle import (
    IllegalIncidentTransition,
    apply_transition,
    project_state,
)
from keel.application.incident.model import (
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentRoute,
    IncidentStatus,
)
from keel.application.incident.routing import route_incident
from keel.application.slo.model import SloEvaluation, SloStatus


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
INCIDENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PIPELINE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
OPEN_EVENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ACK_EVENT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
RESOLVE_EVENT_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
ASSIGN_EVENT_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def _opened(*, incident_id: UUID = INCIDENT_ID, at: datetime = NOW) -> IncidentEvent:
    return IncidentEvent(
        id=OPEN_EVENT_ID,
        incident_id=incident_id,
        type=IncidentEventType.OPENED,
        at=at,
        actor="system",
    )


def _event(
    event_type: IncidentEventType,
    *,
    event_id: UUID = ACK_EVENT_ID,
    at: datetime = NOW + timedelta(minutes=1),
    actor: str = "data-oncall@example.com",
    route: IncidentRoute | None = None,
) -> IncidentEvent:
    return IncidentEvent(
        id=event_id,
        incident_id=INCIDENT_ID,
        type=event_type,
        at=at,
        actor=actor,
        route=route,
    )


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


def _incident() -> Incident:
    return Incident(
        id=INCIDENT_ID,
        subject="raw.orders",
        pipeline_id=PIPELINE_ID,
        slo_name="freshness",
        status=IncidentStatus.OPEN,
        evaluation=_evaluation(),
        run_id=None,
        team="revenue",
        owner="data-oncall@example.com",
        impacted=frozenset({"mart.orders"}),
        opened_at=NOW,
    )


def test_opened_log_projects_to_open_status() -> None:
    state = project_state([_opened()])

    assert state.status is IncidentStatus.OPEN
    assert state.acknowledged_at is None
    assert state.resolved_at is None


def test_acknowledge_transitions_open_to_acknowledged() -> None:
    event = apply_transition(
        events=[_opened()],
        action=IncidentEventType.ACKNOWLEDGED,
        at=NOW + timedelta(minutes=1),
        actor="data-oncall@example.com",
        new_id=ACK_EVENT_ID,
    )

    state = project_state([_opened(), event])

    assert event.type is IncidentEventType.ACKNOWLEDGED
    assert state.status is IncidentStatus.ACKNOWLEDGED


def test_resolve_transitions_acknowledged_to_resolved() -> None:
    acknowledged = _event(IncidentEventType.ACKNOWLEDGED)

    event = apply_transition(
        events=[_opened(), acknowledged],
        action=IncidentEventType.RESOLVED,
        at=NOW + timedelta(minutes=2),
        actor="system",
        new_id=RESOLVE_EVENT_ID,
    )

    state = project_state([_opened(), acknowledged, event])

    assert event.type is IncidentEventType.RESOLVED
    assert state.status is IncidentStatus.RESOLVED


def test_open_can_auto_resolve_without_acknowledge() -> None:
    event = apply_transition(
        events=[_opened()],
        action=IncidentEventType.RESOLVED,
        at=NOW + timedelta(minutes=2),
        actor="system",
        new_id=RESOLVE_EVENT_ID,
    )

    state = project_state([_opened(), event])

    assert state.status is IncidentStatus.RESOLVED
    assert state.acknowledged_at is None


def test_resolved_is_terminal_rejects_further_transitions() -> None:
    resolved = _event(
        IncidentEventType.RESOLVED,
        event_id=RESOLVE_EVENT_ID,
        at=NOW + timedelta(minutes=2),
        actor="system",
    )

    with pytest.raises(IllegalIncidentTransition):
        apply_transition(
            events=[_opened(), resolved],
            action=IncidentEventType.RESOLVED,
            at=NOW + timedelta(minutes=3),
            actor="system",
            new_id=UUID(int=1),
        )


def test_cannot_acknowledge_a_resolved_incident() -> None:
    resolved = _event(
        IncidentEventType.RESOLVED,
        event_id=RESOLVE_EVENT_ID,
        at=NOW + timedelta(minutes=2),
        actor="system",
    )

    with pytest.raises(IllegalIncidentTransition):
        apply_transition(
            events=[_opened(), resolved],
            action=IncidentEventType.ACKNOWLEDGED,
            at=NOW + timedelta(minutes=3),
            actor="data-oncall@example.com",
            new_id=ACK_EVENT_ID,
        )


def test_transition_records_actor_and_timestamp() -> None:
    at = NOW + timedelta(minutes=1)

    event = apply_transition(
        events=[_opened()],
        action=IncidentEventType.ACKNOWLEDGED,
        at=at,
        actor="data-oncall@example.com",
        new_id=ACK_EVENT_ID,
        note="looking now",
    )

    assert event.actor == "data-oncall@example.com"
    assert event.at == at
    assert event.note == "looking now"


def test_project_state_exposes_acknowledged_and_resolved_times() -> None:
    acknowledged_at = NOW + timedelta(minutes=1)
    resolved_at = NOW + timedelta(minutes=2)
    acknowledged = _event(IncidentEventType.ACKNOWLEDGED, at=acknowledged_at)
    resolved = _event(
        IncidentEventType.RESOLVED,
        event_id=RESOLVE_EVENT_ID,
        at=resolved_at,
        actor="system",
    )

    state = project_state([_opened(), acknowledged, resolved])

    assert state.acknowledged_at == acknowledged_at
    assert state.resolved_at == resolved_at


def test_route_incident_derives_owning_team_from_snapshot() -> None:
    route = route_incident(_incident())

    assert route == IncidentRoute(team="revenue", owner="data-oncall@example.com")


def test_assigned_event_does_not_change_lifecycle_status() -> None:
    route = IncidentRoute(team="finance", owner="finance-oncall@example.com")
    assigned = _event(
        IncidentEventType.ASSIGNED,
        event_id=ASSIGN_EVENT_ID,
        actor="system",
        route=route,
    )

    state = project_state([_opened(), assigned])

    assert state.status is IncidentStatus.OPEN
    assert state.assignee == route


def test_event_log_must_start_with_opened() -> None:
    with pytest.raises(IllegalIncidentTransition):
        project_state([_event(IncidentEventType.ACKNOWLEDGED)])
