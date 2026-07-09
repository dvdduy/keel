from __future__ import annotations

from datetime import datetime
from typing import Sequence, assert_never

from keel.application.slo.model import (
    Slo,
    SloEvaluation,
    SloObservation,
    SloOutcome,
    SloStatus,
    UnknownPolicy,
)


def evaluate_slo(
    *,
    slo: Slo,
    observations: Sequence[SloObservation],
    now: datetime,
) -> SloEvaluation:
    if not 0 < slo.objective < 1:
        raise ValueError("objective must be between 0 and 1")

    if slo.window.total_seconds() <= 0:
        raise ValueError("window must be greater than 0")

    _require_timezone_aware("now", now)

    window_start = now - slo.window
    good = 0
    bad = 0
    unknown = 0

    for observation in observations:
        _require_timezone_aware("observation.at", observation.at)

        if observation.at < window_start or observation.at > now:
            continue

        match observation.outcome:
            case SloOutcome.GOOD:
                good += 1
            case SloOutcome.BAD:
                bad += 1
            case SloOutcome.UNKNOWN:
                unknown += 1
            case _ as unhandled_outcome:
                assert_never(unhandled_outcome)

    match slo.unknown_policy:
        case UnknownPolicy.COUNT_AS_BAD:
            total = good + bad + unknown
            consumed = float(bad + unknown)
        case UnknownPolicy.EXCLUDE:
            total = good + bad
            consumed = float(bad)
        case _ as unhandled_policy:
            assert_never(unhandled_policy)

    if total == 0:
        attainment = None
        status = SloStatus.NO_DATA
    else:
        attainment = good / total
        status = SloStatus.MEETING if attainment >= slo.objective else SloStatus.BREACHING

    budget_total = (1 - slo.objective) * total

    return SloEvaluation(
        objective=slo.objective,
        window_start=window_start,
        window_end=now,
        total=total,
        good=good,
        bad=bad,
        unknown=unknown,
        attainment=attainment,
        status=status,
        error_budget_total=budget_total,
        error_budget_consumed=consumed,
        error_budget_remaining=budget_total - consumed,
    )


def _require_timezone_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
