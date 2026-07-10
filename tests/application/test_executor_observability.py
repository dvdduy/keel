from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from keel.adapters.executor.local import LocalExecutor
from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanStep,
    QualityGateStep,
    TransformStep,
)
from keel.application.execution.topology import topological_order
from keel.application.ports.step_handler import Compensation
from keel.application.specs.models import QualityCheckSpec, QualityCheckType
from keel.domain.run import Run, RunStatus, RunStep


@dataclass
class FakeRunRepository:
    added: list[Run] = field(default_factory=list)

    def add(self, run: Run) -> None:
        self.added.append(run)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@dataclass
class FakeStepHandler:
    fail_on: str | None = None
    calls: list[str] = field(default_factory=list)

    def run(self, *, run_id: UUID, step: PlanStep) -> Compensation:
        self.calls.append(step.key)

        if step.key == self.fail_on:
            raise RuntimeError(f"boom: {step.key}")

        return lambda: None


@dataclass
class RecordingObserver:
    events: list[tuple[str, str, RunStatus]] = field(default_factory=list)

    def run_started(self, run: Run) -> None:
        self.events.append(("run_started", str(run.id), run.status))

    def step_started(self, run: Run, step: RunStep) -> None:
        self.events.append(("step_started", step.name, step.status))

    def step_finished(self, run: Run, step: RunStep) -> None:
        self.events.append(("step_finished", step.name, step.status))

    def run_finished(self, run: Run) -> None:
        self.events.append(("run_finished", str(run.id), run.status))


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        steps=(
            QualityGateStep(
                key="quality:not_null:order_id",
                depends_on=frozenset({"transform"}),
                checks=(QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id"),),
                table="raw.orders",
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


def _executor(
    *,
    observer: RecordingObserver | None = None,
    fail_on: str | None = None,
) -> tuple[LocalExecutor, FakeStepHandler]:
    handler = FakeStepHandler(fail_on=fail_on)
    kwargs = {}
    if observer is not None:
        kwargs["observer"] = observer

    return (
        LocalExecutor(
            runs=FakeRunRepository(),
            handler=handler,
            clock=FakeClock(),
            **kwargs,
        ),
        handler,
    )


def test_observer_receives_run_started_then_run_finished() -> None:
    observer = RecordingObserver()
    executor, _ = _executor(observer=observer)

    executor.execute(uuid4(), _plan())

    assert observer.events[0][0] == "run_started"
    assert observer.events[-1][0] == "run_finished"


def test_step_events_fire_in_topological_order() -> None:
    observer = RecordingObserver()
    executor, _ = _executor(observer=observer)
    plan = _plan()

    executor.execute(uuid4(), plan)

    step_started = [name for event, name, _ in observer.events if event == "step_started"]
    assert tuple(step_started) == tuple(step.key for step in topological_order(plan))


def test_step_failure_emits_step_finished_failed_then_run_finished_failed() -> None:
    observer = RecordingObserver()
    executor, _ = _executor(observer=observer, fail_on="transform")

    executor.execute(uuid4(), _plan())

    assert observer.events[-2:] == [
        ("step_finished", "transform", RunStatus.FAILED),
        ("run_finished", observer.events[-1][1], RunStatus.FAILED),
    ]


def test_run_finished_carries_success_status_on_happy_path() -> None:
    observer = RecordingObserver()
    executor, _ = _executor(observer=observer)

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.SUCCESS
    assert observer.events[-1] == ("run_finished", str(run.id), RunStatus.SUCCESS)


def test_every_step_started_has_matching_step_finished_on_failure() -> None:
    observer = RecordingObserver()
    executor, _ = _executor(observer=observer, fail_on="quality:not_null:order_id")

    executor.execute(uuid4(), _plan())

    started = [name for event, name, _ in observer.events if event == "step_started"]
    finished = [name for event, name, _ in observer.events if event == "step_finished"]
    assert finished == started


def test_null_observer_is_default_executor_runs_unobserved() -> None:
    executor, handler = _executor()

    run = executor.execute(uuid4(), _plan())

    assert run.status == RunStatus.SUCCESS
    assert handler.calls == ["ingest", "transform", "quality:not_null:order_id"]
