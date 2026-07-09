from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class SloOutcome(StrEnum):
    GOOD = "good"
    BAD = "bad"
    UNKNOWN = "unknown"


class UnknownPolicy(StrEnum):
    COUNT_AS_BAD = "count_as_bad"
    EXCLUDE = "exclude"


class SloStatus(StrEnum):
    MEETING = "meeting"
    BREACHING = "breaching"
    NO_DATA = "no_data"


@dataclass(frozen=True)
class SloObservation:
    at: datetime
    outcome: SloOutcome


@dataclass(frozen=True)
class Slo:
    objective: float
    window: timedelta
    unknown_policy: UnknownPolicy = UnknownPolicy.COUNT_AS_BAD


@dataclass(frozen=True)
class SloEvaluation:
    objective: float
    window_start: datetime
    window_end: datetime
    total: int
    good: int
    bad: int
    unknown: int
    attainment: float | None
    status: SloStatus
    error_budget_total: float
    error_budget_consumed: float
    error_budget_remaining: float
