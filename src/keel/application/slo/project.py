from __future__ import annotations

from typing import assert_never

from keel.application.quality.checks import CheckStatus
from keel.application.quality.freshness import FreshnessResult, FreshnessStatus
from keel.application.quality.results import QualityResult
from keel.application.slo.model import SloObservation, SloOutcome


def observation_from_freshness(result: FreshnessResult) -> SloObservation:
    if result.as_of is None:
        raise ValueError("freshness result must include an as-of timestamp")

    match result.status:
        case FreshnessStatus.FRESH:
            outcome = SloOutcome.GOOD
        case FreshnessStatus.STALE:
            outcome = SloOutcome.BAD
        case FreshnessStatus.UNKNOWN:
            outcome = SloOutcome.UNKNOWN
        case _ as unhandled:
            assert_never(unhandled)

    return SloObservation(at=result.as_of, outcome=outcome)


def observation_from_quality(result: QualityResult) -> SloObservation:
    match result.status:
        case CheckStatus.PASSED:
            outcome = SloOutcome.GOOD
        case CheckStatus.FAILED:
            outcome = SloOutcome.BAD
        case CheckStatus.UNKNOWN:
            outcome = SloOutcome.UNKNOWN
        case _ as unhandled:
            assert_never(unhandled)

    return SloObservation(at=result.created_at, outcome=outcome)
