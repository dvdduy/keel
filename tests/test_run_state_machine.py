from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from keel.domain.run import IllegalStateTransition, Run, RunStatus, RunStep


def test_run_walks_pending_running_success() -> None:
    created_at = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    run = Run(id=uuid4(), pipeline_id=uuid4(), created_at=created_at)

    assert run.status == RunStatus.PENDING

    run.start(datetime(2026, 7, 8, 12, 0, tzinfo=UTC))
    assert run.status == RunStatus.RUNNING

    run.succeed(datetime(2026, 7, 8, 12, 1, tzinfo=UTC))
    assert run.status == RunStatus.SUCCESS


def test_run_running_to_failed() -> None:
    created_at = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    run = Run(id=uuid4(), pipeline_id=uuid4(), created_at=created_at)

    run.start(datetime(2026, 7, 8, 12, 0, tzinfo=UTC))
    run.fail(datetime(2026, 7, 8, 12, 1, tzinfo=UTC))

    assert run.status == RunStatus.FAILED


@pytest.mark.parametrize(
    ("initial_status", "action"),
    [
        (RunStatus.SUCCESS, "start"),
        (RunStatus.PENDING, "succeed"),
        (RunStatus.PENDING, "fail"),
        (RunStatus.FAILED, "start"),
        (RunStatus.FAILED, "succeed"),
        (RunStatus.FAILED, "fail"),
        (RunStatus.RUNNING, "start"),
    ],
)
def test_illegal_run_transition_raises(initial_status: RunStatus, action: str) -> None:
    created_at = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    run = Run(id=uuid4(), pipeline_id=uuid4(), status=initial_status, created_at=created_at)
    now = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    with pytest.raises(IllegalStateTransition):
        getattr(run, action)(now)


@pytest.mark.parametrize(
    ("initial_status", "action"),
    [
        (RunStatus.SUCCESS, "start"),
        (RunStatus.PENDING, "succeed"),
        (RunStatus.PENDING, "fail"),
        (RunStatus.FAILED, "start"),
        (RunStatus.FAILED, "succeed"),
        (RunStatus.FAILED, "fail"),
        (RunStatus.RUNNING, "start"),
    ],
)
def test_illegal_step_transition_raises(initial_status: RunStatus, action: str) -> None:
    step = RunStep(
        id=uuid4(),
        run_id=uuid4(),
        name="ingest",
        status=initial_status,
        sequence=0,
        created_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(IllegalStateTransition):
        getattr(step, action)()


def test_start_stamps_started_at_and_succeed_stamps_finished_at() -> None:
    created_at = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    run = Run(id=uuid4(), pipeline_id=uuid4(), created_at=created_at)
    started = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    finished = datetime(2026, 7, 8, 12, 5, tzinfo=UTC)

    run.start(started)
    run.succeed(finished)

    assert run.started_at == started
    assert run.finished_at == finished
