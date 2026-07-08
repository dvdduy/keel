# tests/test_drift.py
from __future__ import annotations

from keel.application.reconcile.drift import (
    DriftKind,
    ObservedColumn,
    ObservedSchema,
    detect_drift,
)
from keel.application.specs.models import (
    ColumnType,
    ContractColumn,
    FreshnessSpec,
    PipelineSpec,
    SourceSpec,
    SourceType,
)


def make_spec(
    contract: tuple[ContractColumn, ...] = (
        ContractColumn(name="order_id", type=ColumnType.INTEGER, nullable=False),
        ContractColumn(name="amount", type=ColumnType.DECIMAL),
        ContractColumn(name="created_at", type=ColumnType.TIMESTAMP),
    ),
) -> PipelineSpec:
    return PipelineSpec(
        name="orders_raw",
        team="growth",
        owner="duy@keel.dev",
        source=SourceSpec(type=SourceType.CSV, path="seeds/orders.csv"),
        destination="raw.orders",
        contract=contract,
        freshness=FreshnessSpec(max_age_minutes=60),
    )


def observed_schema(
    columns: tuple[ObservedColumn, ...] = (
        ObservedColumn(name="order_id", type=ColumnType.INTEGER),
        ObservedColumn(name="amount", type=ColumnType.DECIMAL),
        ObservedColumn(name="created_at", type=ColumnType.TIMESTAMP),
    ),
) -> ObservedSchema:
    return ObservedSchema(columns=columns)


def test_in_sync_when_observed_matches_contract() -> None:
    report = detect_drift(make_spec(), observed_schema())

    assert report.table == "raw.orders"
    assert report.in_sync is True
    assert report.drifts == ()


def test_missing_column_when_contract_column_absent_from_table() -> None:
    report = detect_drift(
        make_spec(),
        observed_schema(
            (
                ObservedColumn(name="order_id", type=ColumnType.INTEGER),
                ObservedColumn(name="amount", type=ColumnType.DECIMAL),
            )
        ),
    )

    assert report.in_sync is False
    assert [drift.kind for drift in report.drifts] == [DriftKind.MISSING_COLUMN]
    assert report.drifts[0].column == "created_at"


def test_unexpected_column_when_table_has_undeclared_column() -> None:
    report = detect_drift(
        make_spec(),
        observed_schema(
            (
                ObservedColumn(name="order_id", type=ColumnType.INTEGER),
                ObservedColumn(name="amount", type=ColumnType.DECIMAL),
                ObservedColumn(name="created_at", type=ColumnType.TIMESTAMP),
                ObservedColumn(name="customer_id", type=ColumnType.INTEGER),
            )
        ),
    )

    assert [drift.kind for drift in report.drifts] == [DriftKind.UNEXPECTED_COLUMN]
    assert report.drifts[0].column == "customer_id"


def test_type_mismatch_when_observed_type_differs() -> None:
    report = detect_drift(
        make_spec(),
        observed_schema(
            (
                ObservedColumn(name="order_id", type=ColumnType.STRING),
                ObservedColumn(name="amount", type=ColumnType.DECIMAL),
                ObservedColumn(name="created_at", type=ColumnType.TIMESTAMP),
            )
        ),
    )

    assert [drift.kind for drift in report.drifts] == [DriftKind.TYPE_MISMATCH]
    assert report.drifts[0].column == "order_id"


def test_missing_table_reports_single_drift_not_per_column() -> None:
    report = detect_drift(make_spec(), observed=None)

    assert report.in_sync is False
    assert len(report.drifts) == 1
    assert report.drifts[0].kind == DriftKind.MISSING_TABLE
    assert report.drifts[0].column is None


def test_detects_all_drifts_simultaneously() -> None:
    report = detect_drift(
        make_spec(),
        observed_schema(
            (
                ObservedColumn(name="order_id", type=ColumnType.STRING),
                ObservedColumn(name="customer_id", type=ColumnType.INTEGER),
            )
        ),
    )

    assert [(drift.kind, drift.column) for drift in report.drifts] == [
        (DriftKind.TYPE_MISMATCH, "order_id"),
        (DriftKind.MISSING_COLUMN, "amount"),
        (DriftKind.MISSING_COLUMN, "created_at"),
        (DriftKind.UNEXPECTED_COLUMN, "customer_id"),
    ]


def test_report_preserves_contract_order() -> None:
    spec = make_spec(
        (
            ContractColumn(name="z_col", type=ColumnType.INTEGER),
            ContractColumn(name="a_col", type=ColumnType.STRING),
            ContractColumn(name="m_col", type=ColumnType.BOOLEAN),
        )
    )

    report = detect_drift(spec, ObservedSchema(columns=()))

    assert [drift.column for drift in report.drifts] == [
        "z_col",
        "a_col",
        "m_col",
    ]
