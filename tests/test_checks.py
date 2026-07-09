from __future__ import annotations

from keel.application.quality.checks import (
    CheckStatus,
    ColumnMeasurement,
    evaluate_check,
)
from keel.application.specs.models import QualityCheckSpec, QualityCheckType


def test_not_null_passes_when_no_nulls() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.NOT_NULL),
        measurement=ColumnMeasurement(row_count=3, null_count=0, distinct_count=3),
    )

    assert result.status is CheckStatus.PASSED
    assert result.violations == 0


def test_not_null_fails_reports_null_count() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.NOT_NULL),
        measurement=ColumnMeasurement(row_count=3, null_count=2, distinct_count=1),
    )

    assert result.status is CheckStatus.FAILED
    assert result.violations == 2


def test_unique_passes_when_all_distinct() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.UNIQUE),
        measurement=ColumnMeasurement(row_count=3, null_count=0, distinct_count=3),
    )

    assert result.status is CheckStatus.PASSED
    assert result.violations == 0


def test_unique_fails_reports_duplicate_count() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.UNIQUE),
        measurement=ColumnMeasurement(row_count=5, null_count=0, distinct_count=3),
    )

    assert result.status is CheckStatus.FAILED
    assert result.violations == 2


def test_unique_ignores_nulls() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.UNIQUE),
        measurement=ColumnMeasurement(row_count=5, null_count=2, distinct_count=3),
    )

    assert result.status is CheckStatus.PASSED
    assert result.violations == 0


def test_missing_measurement_is_unknown() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.NOT_NULL),
        measurement=None,
    )

    assert result.status is CheckStatus.UNKNOWN


def test_unknown_result_has_no_violation_count() -> None:
    result = evaluate_check(
        check=_check(QualityCheckType.UNIQUE),
        measurement=None,
    )

    assert result.violations is None


def test_every_check_type_is_handled() -> None:
    measurement = ColumnMeasurement(row_count=1, null_count=0, distinct_count=1)

    for check_type in QualityCheckType:
        result = evaluate_check(
            check=_check(check_type),
            measurement=measurement,
        )

        assert result.check_type is check_type


def _check(check_type: QualityCheckType) -> QualityCheckSpec:
    return QualityCheckSpec(type=check_type, column="order_id")
