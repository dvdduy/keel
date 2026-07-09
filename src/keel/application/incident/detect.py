from __future__ import annotations

from datetime import datetime
from uuid import UUID

from keel.application.incident.model import Incident, IncidentContext, IncidentStatus
from keel.application.slo.model import SloEvaluation, SloStatus


def detect_incident(
    *,
    slo_name: str,
    evaluation: SloEvaluation,
    context: IncidentContext,
    now: datetime,
    new_id: UUID,
) -> Incident | None:
    if evaluation.status is not SloStatus.BREACHING:
        return None

    return Incident(
        id=new_id,
        subject=context.subject,
        pipeline_id=context.pipeline_id,
        slo_name=slo_name,
        status=IncidentStatus.OPEN,
        evaluation=evaluation,
        run_id=context.run.id if context.run else None,
        team=context.team,
        owner=context.owner,
        impacted=context.graph.impacted_by(context.subject),
        opened_at=now,
    )
