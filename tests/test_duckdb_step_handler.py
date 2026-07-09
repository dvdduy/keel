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


def test_failed_plan_drops_successful_ingest_table(tmp_path) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"

    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
    )
    executor = LocalExecutor(
        runs=FakeRunRepository(),
        handler=handler,
        clock=FakeClock(),
    )

    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path=str(Path(__file__).parent / "fixtures" / "orders.csv"),
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

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        assert warehouse.describe_table("raw.orders") is None
    finally:
        warehouse.close()
