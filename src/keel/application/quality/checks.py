from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from keel.application.specs.models import QualityCheckSpec, QualityCheckType


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ColumnMeasurement:
    """Point-in-time facts about one column, measured at the warehouse seam."""

    row_count: int
    null_count: int
    distinct_count: int  # distinct NON-NULL values — SQL count(distinct) semantics


@dataclass(frozen=True)
class CheckResult:
    check_type: QualityCheckType
    column: str
    status: CheckStatus
    detail: str
    violations: int | None  # offending row count; None when UNKNOWN


def evaluate_check(
    *,
    check: QualityCheckSpec,
    measurement: ColumnMeasurement | None,
) -> CheckResult:
    """Judge one quality check against already-measured column facts.

    Pure: no warehouse access, exactly like evaluate_freshness. A None
    measurement (table/column not observable) yields UNKNOWN, never FAILED.
    """

    if measurement is None:
        return CheckResult(
            check_type=check.type,
            column=check.column,
            status=CheckStatus.UNKNOWN,
            detail=(
                f"{check.type.value} check on {check.column} is unknown because "
                "no column measurement was available"
            ),
            violations=None,
        )

    match check.type:
        case QualityCheckType.NOT_NULL:
            return _evaluate_not_null(check=check, measurement=measurement)

        case QualityCheckType.UNIQUE:
            return _evaluate_unique(check=check, measurement=measurement)

        case _ as unhandled:
            assert_never(unhandled)


def _evaluate_not_null(
    *,
    check: QualityCheckSpec,
    measurement: ColumnMeasurement,
) -> CheckResult:
    violations = measurement.null_count

    if violations == 0:
        return CheckResult(
            check_type=check.type,
            column=check.column,
            status=CheckStatus.PASSED,
            detail=f"{check.column} has no NULL values",
            violations=0,
        )

    return CheckResult(
        check_type=check.type,
        column=check.column,
        status=CheckStatus.FAILED,
        detail=f"{check.column} has {violations} NULL value(s)",
        violations=violations,
    )


def _evaluate_unique(
    *,
    check: QualityCheckSpec,
    measurement: ColumnMeasurement,
) -> CheckResult:
    non_null_count = measurement.row_count - measurement.null_count
    violations = non_null_count - measurement.distinct_count

    if violations == 0:
        return CheckResult(
            check_type=check.type,
            column=check.column,
            status=CheckStatus.PASSED,
            detail=(
                f"{check.column} has {measurement.distinct_count} distinct "
                f"non-NULL value(s) across {non_null_count} non-NULL row(s)"
            ),
            violations=0,
        )

    return CheckResult(
        check_type=check.type,
        column=check.column,
        status=CheckStatus.FAILED,
        detail=f"{check.column} has {violations} duplicate non-NULL row(s)",
        violations=violations,
    )
