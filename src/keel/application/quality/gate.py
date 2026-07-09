from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import assert_never
from uuid import UUID, uuid4

from keel.application.ports.quality_results import QualityResultRepository
from keel.application.quality.checks import CheckResult, CheckStatus
from keel.application.quality.results import QualityResult


class GateDecision(StrEnum):
    PROCEED = "proceed"
    BLOCK = "block"


def decide_gate(results: Sequence[CheckResult]) -> GateDecision:
    """Proceed only when every quality check passed."""

    for result in results:
        match result.status:
            case CheckStatus.PASSED:
                continue
            case CheckStatus.FAILED | CheckStatus.UNKNOWN:
                return GateDecision.BLOCK
            case _ as unhandled:
                assert_never(unhandled)

    return GateDecision.PROCEED


def apply_gate(
    *,
    run_id: UUID,
    results: Sequence[CheckResult],
    repository: QualityResultRepository,
    clock: Callable[[], datetime],
) -> GateDecision:
    """Record every check result, then decide whether the gate blocks."""

    for result in results:
        repository.add(
            QualityResult(
                id=uuid4(),
                run_id=run_id,
                check_type=result.check_type,
                column=result.column,
                status=result.status,
                violations=result.violations,
                detail=result.detail,
                created_at=clock(),
            )
        )

    return decide_gate(results)
