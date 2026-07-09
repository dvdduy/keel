from pathlib import Path

import pytest
import duckdb

from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.ports.transform import (
    ManifestNode,
    ModelResult,
    ModelStatus,
    TestReport,
    TestResult,
    TestStatus,
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


def test_passing_dbt_tests_report_ok(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"
    runner = _seed_and_build(tmp_path, warehouse_path, "stg_orders")

    report = runner.test("stg_orders")

    assert report.ok is True
    tests = _tests_by_name(report)
    assert any(test.status == TestStatus.PASS for test in tests.values())


def test_failing_dbt_test_reports_not_ok_with_failure_count(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"
    runner = _seed_and_build(tmp_path, warehouse_path, "+stg_orders_bad_unique")

    report = runner.test("+stg_orders_bad_unique")

    assert report.ok is False
    failed = [test for test in report.tests if test.status == TestStatus.FAIL]
    assert len(failed) == 1
    assert failed[0].failures == 1
    assert "customer_id" in failed[0].test


def test_test_tool_failure_raises_transform_error(tmp_path):
    runner = DbtTransformRunner(
        project_dir=tmp_path / "missing-project",
        warehouse_path=str(tmp_path / "warehouse.duckdb"),
    )

    with pytest.raises(TransformError):
        runner.test("stg_orders")


def test_warn_severity_does_not_block_by_default(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"
    runner = _seed_and_build(tmp_path, warehouse_path, "+stg_orders_warn_unique")

    report = runner.test("+stg_orders_warn_unique")

    assert report.ok is True
    warned = [test for test in report.tests if test.status == TestStatus.WARN]
    assert len(warned) == 1
    assert warned[0].failures == 1


def test_capture_manifest_returns_model_and_source_nodes(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"
    runner = _seed_and_build(tmp_path, warehouse_path, "stg_orders")

    manifest = runner.capture_manifest()

    assert _manifest_node(manifest.nodes, resource_type="model", name="stg_orders") is not None
    assert _manifest_node(manifest.nodes, resource_type="source", name="orders") is not None


def test_capture_manifest_includes_depends_on_edges(tmp_path):
    warehouse_path = tmp_path / "warehouse.duckdb"
    runner = _seed_and_build(tmp_path, warehouse_path, "stg_orders")

    manifest = runner.capture_manifest()

    stg_orders = _manifest_node(manifest.nodes, resource_type="model", name="stg_orders")
    assert stg_orders is not None
    assert any(
        dep.startswith("source.") and dep.endswith(".orders") for dep in stg_orders.depends_on
    )


def test_capture_manifest_missing_artifact_raises_transform_error(tmp_path):
    runner = DbtTransformRunner(
        project_dir=tmp_path,
        warehouse_path=str(tmp_path / "warehouse.duckdb"),
    )

    with pytest.raises(TransformError):
        runner.capture_manifest()


def _seed_and_build(
    tmp_path: Path,
    warehouse_path: Path,
    model: str,
) -> DbtTransformRunner:
    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        warehouse.ingest_csv("raw.orders", FIXTURE)
    finally:
        warehouse.close()

    runner = DbtTransformRunner(
        project_dir=PROJECT_DIR,
        warehouse_path=str(warehouse_path),
    )
    result = runner.run(model)
    assert result.ok is True
    return runner


def _tests_by_name(result: TestReport) -> dict[str, TestResult]:
    return {test.test: test for test in result.tests}


def _manifest_node(
    nodes: tuple[ManifestNode, ...],
    *,
    resource_type: str,
    name: str,
) -> ManifestNode | None:
    for node in nodes:
        if node.resource_type == resource_type and node.name == name:
            return node
    return None
