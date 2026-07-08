from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from keel.adapters.executor.local import LocalExecutor
from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanStep,
    QualityStep,
    TransformStep,
)
from keel.application.execution.topology import topological_order
from keel.application.ports.step_handler import Compensation
from keel.application.specs.models import QualityCheckType
from keel.domain.run import Run, RunStatus


@dataclass
class FakeRunRepository:
    added: list[Run] = field(default_factory=list)

    def add(self, run: Run) -> None:
        self.added.append(run)


@dataclass
class RecordingStepHandler:
    fail_on: str | None = None
    fail_undo_on: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)
    undo_calls: list[str] = field(default_factory=list)

    def run(self, step: PlanStep) -> Compensation:
        self.calls.append(step.key)

        if step.key == self.fail_on:
            raise RuntimeError(f"boom: {step.key}")

        key = step.key

        def compensate() -> None:
            self.undo_calls.append(key)
            if key in self.fail_undo_on:
                raise RuntimeError(f"undo boom: {key}")

        return compensate


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        steps=(
            QualityStep(
                key="quality:not_null:order_id",
                depends_on=frozenset({"transform"}),
                check=QualityCheckType.NOT_NULL,
                column="order_id",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="stg_orders",
            ),
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path="data/orders.csv",
                destination="raw.orders",
            ),
        )
    )


def test_executes_all_steps_in_topological_order() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    plan = _plan()
    executor.execute(uuid4(), plan)

    assert tuple(handler.calls) == tuple(step.key for step in topological_order(plan))


def test_happy_path_run_and_all_steps_success() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.SUCCESS
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
    ]
    assert run.started_at is not None
    assert run.finished_at is not None


def test_failed_step_marks_run_failed() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(fail_on="transform")
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.FAILED
    assert [step.name for step in run.steps] == ["ingest", "transform"]
    assert [step.status for step in run.steps] == [
        RunStatus.SUCCESS,
        RunStatus.FAILED,
    ]


def test_failure_halts_downstream() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(fail_on="transform")
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert handler.calls == ["ingest", "transform"]
    assert [step.name for step in run.steps] == ["ingest", "transform"]
    assert "quality:not_null:order_id" not in handler.calls


def test_run_persisted_via_repository() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert runs.added == [run]


def test_happy_path_runs_no_compensations() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler()
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    executor.execute(uuid4(), _plan())

    assert handler.undo_calls == []


def test_failure_compensates_prior_steps_in_reverse_order() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(fail_on="quality:not_null:order_id")
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.FAILED
    assert handler.calls == ["ingest", "transform", "quality:not_null:order_id"]
    assert handler.undo_calls == ["transform", "ingest"]


def test_first_step_failure_compensates_nothing() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(fail_on="ingest")
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.FAILED
    assert handler.calls == ["ingest"]
    assert handler.undo_calls == []


def test_compensation_failure_does_not_abort_rollback() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(
        fail_on="quality:not_null:order_id",
        fail_undo_on={"transform"},
    )
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.FAILED
    assert handler.undo_calls == ["transform", "ingest"]


def test_run_still_persisted_once_after_rollback() -> None:
    runs = FakeRunRepository()
    handler = RecordingStepHandler(fail_on="quality:not_null:order_id")
    executor = LocalExecutor(runs=runs, handler=handler, clock=FakeClock())

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.FAILED
    assert runs.added == [run]
