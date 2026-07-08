# tests/test_warehouse_drift.py
from __future__ import annotations

from pathlib import Path

import duckdb

from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.reconcile.drift import DriftKind, detect_drift
from keel.application.specs.models import ColumnType
from keel.application.specs.parser import parse_pipeline_spec_file

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CSV_FIXTURE = FIXTURES_DIR / "orders.csv"
SPEC_FIXTURE = FIXTURES_DIR / "orders_raw.yaml"


def test_detect_drift_against_real_duckdb_schema(tmp_path: Path) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))

    spec = parse_pipeline_spec_file(SPEC_FIXTURE)
    warehouse.ingest_csv(spec.destination, CSV_FIXTURE)

    mutated_spec = spec.model_copy(
        update={
            "contract": (
                spec.contract[0],
                spec.contract[1].model_copy(update={"type": ColumnType.STRING}),
                spec.contract[2],
            )
        }
    )

    observed = warehouse.describe_table(mutated_spec.destination)
    report = detect_drift(mutated_spec, observed)

    assert [(drift.kind, drift.column) for drift in report.drifts] == [
        (DriftKind.TYPE_MISMATCH, "amount"),
        (DriftKind.MISSING_COLUMN, "created_at"),
        (DriftKind.UNEXPECTED_COLUMN, "customer_id"),
    ]


def test_describe_table_returns_none_for_missing_duckdb_table(
    tmp_path: Path,
) -> None:
    warehouse = DuckDbWarehouse(str(tmp_path / "warehouse.duckdb"))

    assert warehouse.describe_table("raw.missing_orders") is None


def test_describe_table_translates_decimal_precision_scale(
    tmp_path: Path,
) -> None:
    database = tmp_path / "warehouse.duckdb"

    con = duckdb.connect(database=str(database))
    try:
        con.execute("CREATE SCHEMA raw")
        con.execute("""
            CREATE TABLE raw.decimal_orders (
                amount DECIMAL(18,3)
            )
            """)
    finally:
        con.close()

    warehouse = DuckDbWarehouse(str(database))

    observed = warehouse.describe_table("raw.decimal_orders")

    assert observed is not None
    assert [(column.name, column.type) for column in observed.columns] == [
        ("amount", ColumnType.DECIMAL),
    ]
