from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from keel.application.lineage.graph import LineageGraph
from keel.application.slo.model import SloEvaluation
from keel.domain.run import Run


class IncidentStatus(StrEnum):
    OPEN = "open"


@dataclass(frozen=True)
class Incident:
    id: UUID
    subject: str
    pipeline_id: UUID
    slo_name: str
    status: IncidentStatus
    evaluation: SloEvaluation
    run_id: UUID | None
    team: str
    owner: str
    impacted: frozenset[str]
    opened_at: datetime


@dataclass(frozen=True)
class IncidentContext:
    subject: str
    pipeline_id: UUID
    team: str
    owner: str
    run: Run | None
    graph: LineageGraph
