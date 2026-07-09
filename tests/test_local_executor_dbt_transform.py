from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from keel.adapters.executor.duckdb_step_handler import DuckDbStepHandler
from keel.adapters.executor.local import LocalExecutor
from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.execution.plan import ExecutionPlan, IngestStep, TransformStep
from keel.domain.run import Run, RunStatus


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
