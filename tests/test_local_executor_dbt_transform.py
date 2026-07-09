from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
import pytest

from keel.adapters.executor.local import LocalExecutor
from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.domain.run import Run, RunStatus
from keel.adapters.executor.duckdb_step_handler import (
    DuckDbStepHandler,
    TransformStepFailed,
)
from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    QualityStep,
    TransformStep,
)
from keel.application.specs.models import QualityCheckType
from keel.application.ports.transform import (
    ModelResult,
    ModelStatus,
    TestReport,
    TestResult,
    TestStatus,
    TransformManifest,
    TransformResult,
)


FIXTURE = Path(__file__).parent / "fixtures" / "orders.csv"
PROJECT_DIR = Path(__file__).resolve().parents[1] / "transform"


@dataclass
class FakeRunRepository:
    added: list[Run] = field(default_factory=list)

    def add(self, run: Run) -> None:
        self.added.append(run)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@dataclass
class FakeTransformRunner:
    run_result: TransformResult
    test_report: TestReport
    calls: list[tuple[str, str]] = field(default_factory=list)

    def run(self, select: str) -> TransformResult:
        self.calls.append(("run", select))
        return self.run_result

    def test(self, select: str) -> TestReport:
        self.calls.append(("test", select))
        return self.test_report

    def capture_manifest(self) -> TransformManifest:
        return TransformManifest(nodes=())


def test_local_executor_runs_ingest_then_dbt_transform_end_to_end(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )
    runs = FakeRunRepository()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path=str(FIXTURE),
                destination="raw.orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="stg_orders",
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.SUCCESS
    assert [step.name for step in run.steps] == ["ingest", "transform"]
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
    ]
    assert runs.added == [run]

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        assert warehouse.row_count("raw.orders") == 3
        assert warehouse.row_count("main.stg_orders") == 3
    finally:
        warehouse.close()


def test_local_executor_marks_transform_result_failure_as_failed_step(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )
    runs = FakeRunRepository()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path=str(FIXTURE),
                destination="raw.orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="broken_model",
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.FAILED
    assert [step.name for step in run.steps] == ["ingest", "transform"]
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.FAILED,
    ]


def test_transform_step_builds_target_and_upstream_models(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )

    runs = FakeRunRepository()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path=str(FIXTURE),
                destination="raw.orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="mart_customer_orders",
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.SUCCESS
    assert [step.name for step in run.steps] == ["ingest", "transform"]
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
    ]

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        assert warehouse.row_count("raw.orders") == 3
        assert warehouse.row_count("main.stg_orders") == 3
        assert warehouse.row_count("main.mart_customer_orders") == 2
    finally:
        warehouse.close()


def test_transform_rollback_drops_all_materialized_models(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )

    runs = FakeRunRepository()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path=str(FIXTURE),
                destination="raw.orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="mart_customer_orders",
            ),
            QualityStep(
                key="quality:not_null:order_id",
                depends_on=frozenset({"transform"}),
                check=QualityCheckType.NOT_NULL,
                column="order_id",
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.FAILED
    assert [step.name for step in run.steps] == [
        "ingest",
        "transform",
        "quality:not_null:order_id",
    ]
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
        RunStatus.FAILED,
    ]

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        assert warehouse.describe_table("main.stg_orders") is None
        assert warehouse.describe_table("main.mart_customer_orders") is None
    finally:
        warehouse.close()


def test_marts_model_failure_is_a_failed_step_with_model_detail(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        warehouse.ingest_csv("raw.orders", FIXTURE)
    finally:
        warehouse.close()

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )

    with pytest.raises(TransformStepFailed) as exc:
        handler.run(
            TransformStep(
                key="transform",
                depends_on=frozenset(),
                model="broken_mart_customer_orders",
            )
        )

    assert "broken_mart_customer_orders" in str(exc.value)
    assert "error" in str(exc.value)


def test_transform_step_fails_run_when_dbt_test_fails(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    fake_runner = FakeTransformRunner(
        run_result=TransformResult(
            ok=True,
            models=(
                ModelResult(
                    model="stg_orders",
                    status=ModelStatus.SUCCESS,
                    message=None,
                ),
            ),
        ),
        test_report=TestReport(
            ok=False,
            tests=(
                TestResult(
                    test="unique_stg_orders_customer_id",
                    status=TestStatus.FAIL,
                    failures=1,
                    message=None,
                ),
            ),
        ),
    )

    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=fake_runner,
    )
    runs = FakeRunRepository()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = ExecutionPlan(
        steps=(
            TransformStep(
                key="transform",
                depends_on=frozenset(),
                model="stg_orders",
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.FAILED
    assert [step.status for step in run.steps] == [RunStatus.FAILED]
    assert fake_runner.calls == [
        ("run", "+stg_orders"),
        ("test", "+stg_orders"),
    ]


def test_transform_step_drops_materialization_on_test_failure(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    def warehouse_factory() -> DuckDbWarehouse:
        return DuckDbWarehouse(str(warehouse_path))

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        warehouse.ingest_csv("raw.orders", FIXTURE)
    finally:
        warehouse.close()

    handler = DuckDbStepHandler(
        warehouse_factory=warehouse_factory,
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )

    with pytest.raises(TransformStepFailed) as exc:
        handler.run(
            TransformStep(
                key="transform",
                depends_on=frozenset(),
                model="stg_orders_bad_unique",
            )
        )

    assert "transform test gate failed" in str(exc.value)
    assert "failures=1" in str(exc.value)

    fresh = DuckDbWarehouse(str(warehouse_path))
    try:
        assert fresh.describe_table("raw.orders") is not None
        assert fresh.describe_table("main.stg_orders") is None
        assert fresh.describe_table("main.stg_orders_bad_unique") is None
    finally:
        fresh.close()
