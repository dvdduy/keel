from pathlib import Path

import pytest
import duckdb

from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.ports.transform import (
    ModelResult,
    ModelStatus,
    TransformError,
    TransformResult,
)

FIXTURE = Path(__file__).parent / "fixtures" / "orders.csv"
PROJECT_DIR = Path(__file__).resolve().parents[1] / "transform"


def test_run_materializes_staging_model_from_raw(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        raw_count = warehouse.ingest_csv("raw.orders", FIXTURE)
    finally:
        warehouse.close()

    runner = DbtTransformRunner(
        project_dir=PROJECT_DIR,
        warehouse_path=str(warehouse_path),
    )

    result = runner.run("stg_orders")

    assert result.ok is True
    assert _models_by_name(result)["stg_orders"].status == ModelStatus.SUCCESS

    fresh = DuckDbWarehouse(str(warehouse_path))
    try:
        assert fresh.row_count("main.stg_orders") == raw_count
    finally:
        fresh.close()


def test_model_sql_error_is_a_failed_result_not_an_exception(tmp_path):
    runner = DbtTransformRunner(
        project_dir=PROJECT_DIR,
        warehouse_path=str(tmp_path / "warehouse.duckdb"),
    )

    result = runner.run("broken_model")

    assert result.ok is False
    broken = _models_by_name(result)["broken_model"]
    assert broken.status == ModelStatus.ERROR


def test_tool_failure_raises_keel_transform_error(tmp_path):
    runner = DbtTransformRunner(
        project_dir=tmp_path / "missing-project",
        warehouse_path=str(tmp_path / "warehouse.duckdb"),
    )

    with pytest.raises(TransformError):
        runner.run("stg_orders")


def _models_by_name(result: TransformResult) -> dict[str, ModelResult]:
    return {model.model: model for model in result.models}


def test_run_materializes_marts_through_staging_chain(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        warehouse.ingest_csv("raw.orders", FIXTURE)
    finally:
        warehouse.close()

    runner = DbtTransformRunner(
        project_dir=PROJECT_DIR,
        warehouse_path=str(warehouse_path),
    )

    result = runner.run("+mart_customer_orders")

    assert result.ok is True

    models = _models_by_name(result)
    assert models["stg_orders"].status == ModelStatus.SUCCESS
    assert models["mart_customer_orders"].status == ModelStatus.SUCCESS

    fresh = DuckDbWarehouse(str(warehouse_path))
    try:
        assert fresh.describe_table("main.stg_orders") is not None
        assert fresh.describe_table("main.mart_customer_orders") is not None
        assert fresh.row_count("main.mart_customer_orders") == 2
    finally:
        fresh.close()

    with duckdb.connect(str(warehouse_path), read_only=True) as con:
        rows = con.execute(
            """
            select customer_id, order_count, total_amount
            from main.mart_customer_orders
            order by customer_id
            """
        ).fetchall()

    assert rows[0][0] == 7
    assert rows[0][1] == 1
    assert float(rows[0][2]) == pytest.approx(120.50)

    assert rows[1][0] == 42
    assert rows[1][1] == 2
    assert float(rows[1][2]) == pytest.approx(24.99)
