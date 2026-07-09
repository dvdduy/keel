from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from keel.application.quality.freshness import FreshnessStatus, evaluate_freshness


def test_within_threshold_is_fresh() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    as_of = now - timedelta(minutes=30)

    result = evaluate_freshness(max_age_minutes=60, as_of=as_of, now=now)

    assert result.status == FreshnessStatus.FRESH
    assert result.max_age_minutes == 60
    assert result.age_minutes == 30.0
    assert result.as_of == as_of
    assert "within" in result.detail


def test_beyond_threshold_is_stale() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    as_of = now - timedelta(minutes=61)

    result = evaluate_freshness(max_age_minutes=60, as_of=as_of, now=now)

    assert result.status == FreshnessStatus.STALE
    assert result.max_age_minutes == 60
    assert result.age_minutes == 61.0
    assert result.as_of == as_of
    assert "exceeds" in result.detail


def test_exactly_at_threshold() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    as_of = now - timedelta(minutes=60)

    result = evaluate_freshness(max_age_minutes=60, as_of=as_of, now=now)

    assert result.status == FreshnessStatus.FRESH
    assert result.age_minutes == 60.0


def test_missing_as_of_is_unknown() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)

    result = evaluate_freshness(max_age_minutes=60, as_of=None, now=now)

    assert result.status == FreshnessStatus.UNKNOWN
    assert result.age_minutes is None
    assert result.as_of is None
    assert "no as-of timestamp" in result.detail


def test_future_as_of_is_handled() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    as_of = now + timedelta(minutes=1)

    result = evaluate_freshness(max_age_minutes=60, as_of=as_of, now=now)

    assert result.status == FreshnessStatus.UNKNOWN
    assert result.age_minutes is None
    assert result.as_of == as_of
    assert "future" in result.detail


def test_naive_datetime_rejected() -> None:
    aware_now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    naive_now = datetime(2026, 7, 8, 12, 0)
    naive_as_of = datetime(2026, 7, 8, 11, 0)

    with pytest.raises(ValueError, match="now must be timezone-aware"):
        evaluate_freshness(max_age_minutes=60, as_of=aware_now, now=naive_now)

    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        evaluate_freshness(max_age_minutes=60, as_of=naive_as_of, now=aware_now)


def test_age_minutes_reported_for_stale() -> None:
    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    as_of = now - timedelta(minutes=75)

    result = evaluate_freshness(max_age_minutes=60, as_of=as_of, now=now)

    assert result.status == FreshnessStatus.STALE
    assert result.age_minutes == 75.0
