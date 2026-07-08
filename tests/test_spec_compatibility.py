from __future__ import annotations

from keel.application.specs.compatibility import (
    BreakingKind,
    CompatibilityReport,
    check_compatibility,
)
from keel.application.specs.models import (
    ColumnType,
    ContractColumn,
    FreshnessSpec,
    PipelineSpec,
    SourceSpec,
    SourceType,
)


def _column(
    name: str,
    column_type: ColumnType,
    *,
    nullable: bool,
) -> ContractColumn:
    return ContractColumn(name=name, type=column_type, nullable=nullable)


def _spec(columns: list[ContractColumn]) -> PipelineSpec:
    return PipelineSpec(
        name="orders_daily",
        team="analytics",
        owner="data-platform@example.com",
        source=SourceSpec(type=SourceType.CSV, path="tests/fixtures/orders.csv"),
        destination="analytics.orders",
        contract=tuple(columns),
        freshness=FreshnessSpec(max_age_minutes=60),
    )


def _kinds(report: CompatibilityReport) -> set[BreakingKind]:
    return {change.kind for change in report.breaking_changes}


def test_identical_contract_is_compatible() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("amount", ColumnType.DECIMAL, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("amount", ColumnType.DECIMAL, nullable=True),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is True
    assert report.breaking_changes == ()


def test_add_nullable_column_is_compatible() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("notes", ColumnType.STRING, nullable=True),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is True
    assert report.breaking_changes == ()


def test_widen_integer_to_decimal_is_compatible() -> None:
    previous = _spec(
        [
            _column("quantity", ColumnType.INTEGER, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("quantity", ColumnType.DECIMAL, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is True
    assert report.breaking_changes == ()


def test_relax_not_null_to_nullable_is_compatible() -> None:
    previous = _spec(
        [
            _column("customer_id", ColumnType.STRING, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("customer_id", ColumnType.STRING, nullable=True),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is True
    assert report.breaking_changes == ()


def test_column_reorder_is_compatible() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("customer_id", ColumnType.STRING, nullable=False),
            _column("amount", ColumnType.DECIMAL, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("amount", ColumnType.DECIMAL, nullable=True),
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("customer_id", ColumnType.STRING, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is True
    assert report.breaking_changes == ()


def test_drop_column_is_breaking() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("amount", ColumnType.DECIMAL, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {BreakingKind.COLUMN_DROPPED}
    assert report.breaking_changes[0].column == "amount"


def test_rename_column_reports_drop() -> None:
    previous = _spec(
        [
            _column("customer_id", ColumnType.STRING, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("client_id", ColumnType.STRING, nullable=True),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert len(report.breaking_changes) == 1
    assert report.breaking_changes[0].kind == BreakingKind.COLUMN_DROPPED
    assert report.breaking_changes[0].column == "customer_id"


def test_narrow_decimal_to_integer_is_breaking() -> None:
    previous = _spec(
        [
            _column("amount", ColumnType.DECIMAL, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("amount", ColumnType.INTEGER, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {BreakingKind.COLUMN_TYPE_CHANGED}
    assert report.breaking_changes[0].column == "amount"


def test_unrelated_type_change_is_breaking() -> None:
    previous = _spec(
        [
            _column("status", ColumnType.STRING, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("status", ColumnType.INTEGER, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {BreakingKind.COLUMN_TYPE_CHANGED}
    assert report.breaking_changes[0].column == "status"


def test_tighten_nullable_to_not_null_is_breaking() -> None:
    previous = _spec(
        [
            _column("notes", ColumnType.STRING, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("notes", ColumnType.STRING, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {BreakingKind.COLUMN_MADE_REQUIRED}
    assert report.breaking_changes[0].column == "notes"


def test_add_required_column_is_breaking() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
        ]
    )
    proposed = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("region", ColumnType.STRING, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {BreakingKind.REQUIRED_COLUMN_ADDED}
    assert report.breaking_changes[0].column == "region"


def test_reports_all_breaking_changes() -> None:
    previous = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("amount", ColumnType.DECIMAL, nullable=False),
            _column("notes", ColumnType.STRING, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("order_id", ColumnType.INTEGER, nullable=False),
            _column("amount", ColumnType.INTEGER, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert _kinds(report) == {
        BreakingKind.COLUMN_TYPE_CHANGED,
        BreakingKind.COLUMN_DROPPED,
    }
    assert len(report.breaking_changes) == 2


def test_single_column_multiple_breaks() -> None:
    previous = _spec(
        [
            _column("amount", ColumnType.DECIMAL, nullable=True),
        ]
    )
    proposed = _spec(
        [
            _column("amount", ColumnType.INTEGER, nullable=False),
        ]
    )

    report = check_compatibility(previous, proposed)

    assert report.compatible is False
    assert len(report.breaking_changes) == 2
    assert _kinds(report) == {
        BreakingKind.COLUMN_TYPE_CHANGED,
        BreakingKind.COLUMN_MADE_REQUIRED,
    }
    assert [change.column for change in report.breaking_changes] == [
        "amount",
        "amount",
    ]
