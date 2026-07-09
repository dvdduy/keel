from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from keel.application.quality.checks import CheckStatus
from keel.application.specs.models import QualityCheckType


@dataclass(frozen=True)
class QualityResult:
    id: UUID
    run_id: UUID
    check_type: QualityCheckType
    column: str
    status: CheckStatus
    violations: int | None
    detail: str
    created_at: datetime
