from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from keel.application.incident.model import (
    IncidentEvent,
    IncidentEventType,
    IncidentState,
    IncidentStatus,
)


class IllegalIncidentTransition(Exception):
    """Raised when an incident event log attempts an invalid lifecycle transition."""


def project_state(events: Sequence[IncidentEvent]) -> IncidentState:
    """Fold the append-only log into current incident state."""
    if not events:
        raise IllegalIncidentTransition("incident event log must start with opened")

    first = events[0]
    if first.type is not IncidentEventType.OPENED:
        raise IllegalIncidentTransition(
            f"incident event log must start with opened; found {first.type.value}"
        )

    state = IncidentState(
        status=IncidentStatus.OPEN,
        acknowledged_at=None,
        resolved_at=None,
        assignee=None,
    )

    for event in events[1:]:
        state = _apply_projected_event(state, event)

    return state


def apply_transition(
    *,
    events: Sequence[IncidentEvent],
    action: IncidentEventType,
    at: datetime,
    actor: str,
    new_id: UUID,
    note: str | None = None,
) -> IncidentEvent:
    """Validate an incident action and return the event to append."""
    if action is IncidentEventType.ASSIGNED:
        raise IllegalIncidentTransition("use routing to create assigned events")
    if action is IncidentEventType.OPENED:
        raise IllegalIncidentTransition("opened is the first event, not a transition")

    state = project_state(events)
    incident_id = events[0].incident_id

    if state.status is IncidentStatus.RESOLVED:
        raise IllegalIncidentTransition("resolved incidents are terminal")
    if action is IncidentEventType.ACKNOWLEDGED and state.status is not IncidentStatus.OPEN:
        raise IllegalIncidentTransition(
            f"cannot acknowledge incident from {state.status.value}; expected open"
        )
    if action is IncidentEventType.RESOLVED and state.status not in {
        IncidentStatus.OPEN,
        IncidentStatus.ACKNOWLEDGED,
    }:
        raise IllegalIncidentTransition(
            f"cannot resolve incident from {state.status.value}; expected open or acknowledged"
        )

    return IncidentEvent(
        id=new_id,
        incident_id=incident_id,
        type=action,
        at=at,
        actor=actor,
        note=note,
    )


def _apply_projected_event(state: IncidentState, event: IncidentEvent) -> IncidentState:
    if event.type is IncidentEventType.OPENED:
        raise IllegalIncidentTransition("opened can only be the first incident event")
    if event.type is IncidentEventType.ASSIGNED:
        return IncidentState(
            status=state.status,
            acknowledged_at=state.acknowledged_at,
            resolved_at=state.resolved_at,
            assignee=event.route,
        )
    if state.status is IncidentStatus.RESOLVED:
        raise IllegalIncidentTransition("resolved incidents are terminal")
    if event.type is IncidentEventType.ACKNOWLEDGED:
        if state.status is not IncidentStatus.OPEN:
            raise IllegalIncidentTransition(
                f"cannot acknowledge incident from {state.status.value}; expected open"
            )
        return IncidentState(
            status=IncidentStatus.ACKNOWLEDGED,
            acknowledged_at=event.at,
            resolved_at=state.resolved_at,
            assignee=state.assignee,
        )
    if event.type is IncidentEventType.RESOLVED:
        return IncidentState(
            status=IncidentStatus.RESOLVED,
            acknowledged_at=state.acknowledged_at,
            resolved_at=event.at,
            assignee=state.assignee,
        )

    raise IllegalIncidentTransition(f"unknown incident event type {event.type.value}")
