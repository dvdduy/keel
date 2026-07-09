from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from keel.adapters.executor.duckdb_step_handler import DuckDbStepHandler
from keel.adapters.executor.local import LocalExecutor
from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.execution.plan import ExecutionPlan, IngestStep, QualityGateStep
from keel.application.quality.checks import CheckStatus
from keel.application.specs.models import QualityCheckSpec, QualityCheckType
from keel.application.quality.results import QualityResult
from keel.domain.run import Run, RunStatus

PROJECT_DIR = Path(__file__).resolve().parents[1] / "transform"


@dataclass
class FakeRunRepository:
    added: list[Run] = field(default_factory=list)

    def add(self, run: Run) -> None:
        self.added.append(run)


@dataclass
class FakeQualityResultRepository:
    added: list[QualityResult] = field(default_factory=list)

    def add(self, result: QualityResult) -> None:
        self.added.append(result)

    def for_run(self, run_id: UUID) -> tuple[QualityResult, ...]:
        return tuple(result for result in self.added if result.run_id == run_id)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def test_duplicate_key_blocks_and_quarantines(tmp_path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(
        "order_id,customer_id,amount\n" "1,10,12.50\n" "1,20,14.00\n",
        encoding="utf-8",
    )

    warehouse_path = tmp_path / "warehouse.duckdb"
    quality_results = FakeQualityResultRepository()

    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
        results=quality_results,
        clock=FakeClock(),
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
                source_path=str(source),
                destination="raw.orders",
            ),
            QualityGateStep(
                key="quality",
                depends_on=frozenset({"ingest"}),
                table="raw.orders",
                checks=(
                    QualityCheckSpec(
                        type=QualityCheckType.UNIQUE,
                        column="order_id",
                    ),
                ),
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

    recorded = quality_results.for_run(run.id)
    assert len(recorded) == 1
    assert recorded[0].status == CheckStatus.FAILED
    assert recorded[0].violations == 1


def test_clean_data_proceeds_and_records_passed(tmp_path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(
        "order_id,customer_id,amount\n" "1,10,12.50\n" "2,20,14.00\n",
        encoding="utf-8",
    )

    warehouse_path = tmp_path / "warehouse.duckdb"
    quality_results = FakeQualityResultRepository()

    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
        results=quality_results,
        clock=FakeClock(),
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
                source_path=str(source),
                destination="raw.orders",
            ),
            QualityGateStep(
                key="quality",
                depends_on=frozenset({"ingest"}),
                table="raw.orders",
                checks=(
                    QualityCheckSpec(
                        type=QualityCheckType.UNIQUE,
                        column="order_id",
                    ),
                ),
            ),
        )
    )

    run = executor.execute(uuid4(), plan)

    assert run.status == RunStatus.SUCCESS

    warehouse = DuckDbWarehouse(str(warehouse_path))
    try:
        assert warehouse.describe_table("raw.orders") is not None
    finally:
        warehouse.close()

    recorded = quality_results.for_run(run.id)
    assert len(recorded) == 1
    assert recorded[0].status == CheckStatus.PASSED
    assert recorded[0].violations == 0


def test_multiple_checks_all_recorded_before_quarantine(tmp_path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(
        "order_id,customer_id,amount\n" "1,,12.50\n" "1,20,14.00\n",
        encoding="utf-8",
    )

    warehouse_path = tmp_path / "warehouse.duckdb"
    quality_results = FakeQualityResultRepository()

    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=DbtTransformRunner(
            project_dir=PROJECT_DIR,
            warehouse_path=str(warehouse_path),
        ),
        results=quality_results,
        clock=FakeClock(),
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
                source_path=str(source),
                destination="raw.orders",
            ),
            QualityGateStep(
                key="quality",
                depends_on=frozenset({"ingest"}),
                table="raw.orders",
                checks=(
                    QualityCheckSpec(
                        type=QualityCheckType.UNIQUE,
                        column="order_id",
                    ),
                    QualityCheckSpec(
                        type=QualityCheckType.NOT_NULL,
                        column="customer_id",
                    ),
                    QualityCheckSpec(
                        type=QualityCheckType.NOT_NULL,
                        column="amount",
                    ),
                ),
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

    recorded = quality_results.for_run(run.id)

    assert len(recorded) == 3
    assert [result.status for result in recorded] == [
        CheckStatus.FAILED,
        CheckStatus.FAILED,
        CheckStatus.PASSED,
    ]
