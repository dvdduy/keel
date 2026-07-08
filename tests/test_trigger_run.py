from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from keel.application.execution.plan import ExecutionPlan
from keel.application.use_cases.trigger_run import TriggerRun
from keel.domain.run import Run, RunKey, RunStatus, is_replayable

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
PLAN = cast(ExecutionPlan, object())


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: list[Run] = []

    def add(self, run: Run) -> None:
        self.runs.append(run)

    def get(self, run_id: UUID) -> Run | None:
        return next((run for run in self.runs if run.id == run_id), None)

    def latest_for_key(self, key: RunKey) -> Run | None:
        matches = [
            run
            for run in self.runs
            if run.pipeline_id == key.pipeline_id and run.watermark == key.watermark
        ]
        return matches[-1] if matches else None


class SpyExecutor:
    def __init__(self, runs: FakeRunRepository) -> None:
        self.runs = runs
        self.calls = 0

    def execute(
        self,
        pipeline_id: UUID,
        plan: ExecutionPlan,
        *,
        watermark: str | None = None,
    ) -> Run:
        self.calls += 1

        run = Run(
            id=uuid4(),
            pipeline_id=pipeline_id,
            created_at=NOW,
            status=RunStatus.SUCCESS,
            watermark=watermark,
        )

        self.runs.add(run)
        return run


def make_run(
    *,
    pipeline_id: UUID,
    watermark: str,
    status: RunStatus,
) -> Run:
    return Run(
        id=uuid4(),
        pipeline_id=pipeline_id,
        created_at=NOW,
        status=status,
        watermark=watermark,
    )


def test_first_trigger_executes_and_persists() -> None:
    pipeline_id = uuid4()
    key = RunKey(pipeline_id=pipeline_id, watermark="2026-07-08")
    runs = FakeRunRepository()
    executor = SpyExecutor(runs)
    use_case = TriggerRun(runs=runs, executor=executor)

    result = use_case.trigger(key, PLAN)

    assert result.executed is True
    assert executor.calls == 1
    assert result.run.pipeline_id == pipeline_id
    assert result.run.watermark == "2026-07-08"
    assert runs.latest_for_key(key) == result.run


def test_identical_retrigger_returns_existing_without_executing() -> None:
    pipeline_id = uuid4()
    key = RunKey(pipeline_id=pipeline_id, watermark="2026-07-08")
    runs = FakeRunRepository()
    executor = SpyExecutor(runs)
    use_case = TriggerRun(runs=runs, executor=executor)

    first = use_case.trigger(key, PLAN)
    second = use_case.trigger(key, PLAN)

    assert first.executed is True
    assert second.executed is False
    assert second.run == first.run
    assert executor.calls == 1


def test_retrigger_after_failed_run_re_executes() -> None:
    pipeline_id = uuid4()
    key = RunKey(pipeline_id=pipeline_id, watermark="2026-07-08")
    runs = FakeRunRepository()
    failed = make_run(
        pipeline_id=pipeline_id,
        watermark="2026-07-08",
        status=RunStatus.FAILED,
    )
    runs.add(failed)

    executor = SpyExecutor(runs)
    use_case = TriggerRun(runs=runs, executor=executor)

    result = use_case.trigger(key, PLAN)

    assert result.executed is True
    assert result.run.id != failed.id
    assert result.run.status is RunStatus.SUCCESS
    assert executor.calls == 1


def test_distinct_watermark_is_a_distinct_run() -> None:
    pipeline_id = uuid4()
    runs = FakeRunRepository()
    executor = SpyExecutor(runs)
    use_case = TriggerRun(runs=runs, executor=executor)

    first = use_case.trigger(
        RunKey(pipeline_id=pipeline_id, watermark="2026-07-08"),
        PLAN,
    )
    second = use_case.trigger(
        RunKey(pipeline_id=pipeline_id, watermark="2026-07-09"),
        PLAN,
    )

    assert first.executed is True
    assert second.executed is True
    assert first.run.id != second.run.id
    assert executor.calls == 2


@pytest.mark.parametrize(
    ("existing_status", "expected"),
    [
        (None, True),
        (RunStatus.PENDING, True),
        (RunStatus.RUNNING, True),
        (RunStatus.FAILED, True),
        (RunStatus.SUCCESS, False),
    ],
)
def test_is_replayable_over_all_statuses(
    existing_status: RunStatus | None,
    expected: bool,
) -> None:
    existing = (
        None
        if existing_status is None
        else make_run(
            pipeline_id=uuid4(),
            watermark="2026-07-08",
            status=existing_status,
        )
    )

    assert is_replayable(existing) is expected
