from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keel.application.slo.evaluate import evaluate_slo
from keel.application.slo.model import (
    Slo,
    SloObservation,
    SloOutcome,
    SloStatus,
    UnknownPolicy,
)


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _slo(*, objective: float = 0.9, unknown_policy: UnknownPolicy | None = None) -> Slo:
    if unknown_policy is None:
        return Slo(objective=objective, window=timedelta(days=30))
    return Slo(
        objective=objective,
        window=timedelta(days=30),
        unknown_policy=unknown_policy,
    )


def _observation(days_ago: int, outcome: SloOutcome) -> SloObservation:
    return SloObservation(at=NOW - timedelta(days=days_ago), outcome=outcome)


def test_all_good_meets_objective() -> None:
    result = evaluate_slo(
        slo=_slo(),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.GOOD),
        ],
        now=NOW,
    )

    assert result.status == SloStatus.MEETING
    assert result.attainment == 1.0
    assert result.total == 2
    assert result.good == 2
    assert result.bad == 0
    assert result.unknown == 0


def test_below_objective_breaches() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.GOOD),
            _observation(3, SloOutcome.BAD),
            _observation(4, SloOutcome.BAD),
        ],
        now=NOW,
    )

    assert result.status == SloStatus.BREACHING
    assert result.attainment == 0.5


def test_attainment_exactly_at_objective_meets() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.GOOD),
            _observation(3, SloOutcome.GOOD),
            _observation(4, SloOutcome.BAD),
        ],
        now=NOW,
    )

    assert result.status == SloStatus.MEETING
    assert result.attainment == 0.75


def test_empty_window_is_no_data_not_meeting() -> None:
    result = evaluate_slo(
        slo=_slo(),
        observations=[],
        now=NOW,
    )

    assert result.status == SloStatus.NO_DATA
    assert result.attainment is None
    assert result.total == 0


def test_observations_outside_window_excluded() -> None:
    result = evaluate_slo(
        slo=Slo(objective=0.5, window=timedelta(days=30)),
        observations=[
            SloObservation(at=NOW - timedelta(days=30), outcome=SloOutcome.GOOD),
            SloObservation(at=NOW, outcome=SloOutcome.GOOD),
            SloObservation(at=NOW - timedelta(days=30, seconds=1), outcome=SloOutcome.BAD),
            SloObservation(at=NOW + timedelta(seconds=1), outcome=SloOutcome.BAD),
        ],
        now=NOW,
    )

    assert result.window_start == NOW - timedelta(days=30)
    assert result.window_end == NOW
    assert result.total == 2
    assert result.good == 2
    assert result.bad == 0


def test_error_budget_total_is_allowed_bad_count() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.GOOD),
            _observation(3, SloOutcome.GOOD),
            _observation(4, SloOutcome.BAD),
        ],
        now=NOW,
    )

    assert result.error_budget_total == 1.0
    assert result.error_budget_consumed == 1.0
    assert result.error_budget_remaining == 0.0


def test_budget_can_go_negative_when_over_spent() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.BAD),
            _observation(3, SloOutcome.BAD),
            _observation(4, SloOutcome.BAD),
        ],
        now=NOW,
    )

    assert result.error_budget_total == 1.0
    assert result.error_budget_consumed == 3.0
    assert result.error_budget_remaining == -2.0


def test_unknown_counts_as_bad_by_default() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.GOOD),
            _observation(3, SloOutcome.GOOD),
            _observation(4, SloOutcome.UNKNOWN),
        ],
        now=NOW,
    )

    assert result.total == 4
    assert result.unknown == 1
    assert result.attainment == 0.75
    assert result.error_budget_consumed == 1.0


def test_unknown_excluded_shrinks_denominator() -> None:
    result = evaluate_slo(
        slo=_slo(objective=0.75, unknown_policy=UnknownPolicy.EXCLUDE),
        observations=[
            _observation(1, SloOutcome.GOOD),
            _observation(2, SloOutcome.BAD),
            _observation(3, SloOutcome.UNKNOWN),
        ],
        now=NOW,
    )

    assert result.total == 2
    assert result.unknown == 1
    assert result.attainment == 0.5
    assert result.error_budget_total == 0.5
    assert result.error_budget_consumed == 1.0


def test_naive_now_raises() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        evaluate_slo(
            slo=_slo(),
            observations=[],
            now=datetime(2026, 7, 9, 12, 0),
        )


def test_naive_observation_raises() -> None:
    with pytest.raises(ValueError, match="observation.at must be timezone-aware"):
        evaluate_slo(
            slo=_slo(),
            observations=[
                SloObservation(
                    at=datetime(2026, 7, 9, 12, 0),
                    outcome=SloOutcome.GOOD,
                )
            ],
            now=NOW,
        )


@pytest.mark.parametrize("objective", [0.0, 1.0, -0.1, 1.1])
def test_objective_out_of_range_raises(objective: float) -> None:
    with pytest.raises(ValueError, match="objective must be between 0 and 1"):
        evaluate_slo(
            slo=Slo(objective=objective, window=timedelta(days=30)),
            observations=[],
            now=NOW,
        )


@pytest.mark.parametrize("window", [timedelta(0), timedelta(seconds=-1)])
def test_nonpositive_window_raises(window: timedelta) -> None:
    with pytest.raises(ValueError, match="window must be greater than 0"):
        evaluate_slo(
            slo=Slo(objective=0.9, window=window),
            observations=[],
            now=NOW,
        )
