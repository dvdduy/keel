from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FreshnessResult:
    status: FreshnessStatus
    max_age_minutes: int
    age_minutes: float | None
    as_of: datetime | None
    detail: str


def evaluate_freshness(
    *,
    max_age_minutes: int,
    as_of: datetime | None,
    now: datetime,
) -> FreshnessResult:
    """Evaluate freshness from an already-resolved freshness clock.

    The caller decides which clock produced `as_of`:
    event-time watermark, wall-clock load time, or another future policy.
    This function only applies source-agnostic freshness arithmetic.
    """
    if max_age_minutes <= 0:
        raise ValueError("max_age_minutes must be greater than 0")

    _require_timezone_aware("now", now)

    if as_of is None:
        return FreshnessResult(
            status=FreshnessStatus.UNKNOWN,
            max_age_minutes=max_age_minutes,
            age_minutes=None,
            as_of=None,
            detail="freshness is unknown because no as-of timestamp was available",
        )

    _require_timezone_aware("as_of", as_of)

    if as_of > now:
        return FreshnessResult(
            status=FreshnessStatus.UNKNOWN,
            max_age_minutes=max_age_minutes,
            age_minutes=None,
            as_of=as_of,
            detail="freshness is unknown because the as-of timestamp is in the future",
        )

    age_minutes = (now - as_of).total_seconds() / 60

    if age_minutes <= max_age_minutes:
        return FreshnessResult(
            status=FreshnessStatus.FRESH,
            max_age_minutes=max_age_minutes,
            age_minutes=age_minutes,
            as_of=as_of,
            detail=(
                f"freshness age {age_minutes:.2f} minutes is within "
                f"the {max_age_minutes} minute threshold"
            ),
        )

    return FreshnessResult(
        status=FreshnessStatus.STALE,
        max_age_minutes=max_age_minutes,
        age_minutes=age_minutes,
        as_of=as_of,
        detail=(
            f"freshness age {age_minutes:.2f} minutes exceeds "
            f"the {max_age_minutes} minute threshold"
        ),
    )


def _require_timezone_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
