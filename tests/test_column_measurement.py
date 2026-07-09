from __future__ import annotations

from pathlib import Path

from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.quality.checks import CheckStatus, ColumnMeasurement, evaluate_check
from keel.application.quality.measure import measure_column
from keel.application.specs.models import QualityCheckSpec, QualityCheckType


def test_clean_column_measures_correctly(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))
    try:
        _seed_orders(warehouse)

        assert measure_column(
            warehouse=warehouse,
            table="raw.orders",
            column="customer_id",
        ) == ColumnMeasurement(
            row_count=3,
            null_count=0,
            distinct_count=3,
        )
    finally:
        warehouse.close()


def test_seeded_bad_data_measures_nulls_and_duplicates(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))
    try:
        _seed_orders(warehouse)

        duplicated = measure_column(
            warehouse=warehouse,
            table="raw.orders",
            column="order_id",
        )
        nullable = measure_column(
            warehouse=warehouse,
            table="raw.orders",
            column="email",
        )

        assert duplicated == ColumnMeasurement(row_count=3, null_count=0, distinct_count=2)
        assert nullable == ColumnMeasurement(row_count=3, null_count=1, distinct_count=2)
    finally:
        warehouse.close()


def test_missing_table_returns_none(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))
    try:
        assert (
            measure_column(
                warehouse=warehouse,
                table="raw.missing_orders",
                column="order_id",
            )
            is None
        )
    finally:
        warehouse.close()


def test_missing_column_returns_none(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))
    try:
        _seed_orders(warehouse)

        assert (
            measure_column(
                warehouse=warehouse,
                table="raw.orders",
                column="missing_column",
            )
            is None
        )
    finally:
        warehouse.close()


def test_measure_then_evaluate_failed_dirty_column_and_passed_clean_column(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))
    try:
        _seed_orders(warehouse)

        dirty_result = evaluate_check(
            check=QualityCheckSpec(type=QualityCheckType.UNIQUE, column="order_id"),
            measurement=measure_column(
                warehouse=warehouse,
                table="raw.orders",
                column="order_id",
            ),
        )
        clean_result = evaluate_check(
            check=QualityCheckSpec(type=QualityCheckType.UNIQUE, column="customer_id"),
            measurement=measure_column(
                warehouse=warehouse,
                table="raw.orders",
                column="customer_id",
            ),
        )

        assert dirty_result.status is CheckStatus.FAILED
        assert dirty_result.violations == 1
        assert clean_result.status is CheckStatus.PASSED
        assert clean_result.violations == 0
    finally:
        warehouse.close()


def _seed_orders(warehouse: DuckDbWarehouse) -> None:
    warehouse._con.execute("CREATE SCHEMA raw")
    warehouse._con.execute(
        """
        CREATE TABLE raw.orders AS
        SELECT *
        FROM (
            VALUES
                (1, 10, 'a@example.com'),
                (1, 20, NULL),
                (3, 30, 'c@example.com')
        ) AS orders(order_id, customer_id, email)
        """
    )
