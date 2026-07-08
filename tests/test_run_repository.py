from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from keel.adapters.db.models import PipelineRecord, TeamRecord, RunRecord
from keel.adapters.db.run_repository import SqlAlchemyRunRepository
from keel.application.execution.plan import ExecutionPlan
from keel.application.use_cases.trigger_run import TriggerRun
from keel.domain.run import Run, RunStatus, RunStep, RunKey

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
PLAN = cast(ExecutionPlan, object())


class SpyExecutor:
    def __init__(self, runs: SqlAlchemyRunRepository) -> None:
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


def _seed_pipeline(session: Session) -> UUID:
    team = TeamRecord(id=uuid4(), name="analytics", created_at=NOW)
    session.add(team)
    session.flush()

    pipeline = PipelineRecord(id=uuid4(), team_id=team.id, name="orders", created_at=NOW)
    session.add_all([team, pipeline])
    session.flush()
    return pipeline.id


def _make_run(pipeline_id: UUID) -> Run:
    run_id = uuid4()
    return Run(
        id=run_id,
        pipeline_id=pipeline_id,
        status=RunStatus.RUNNING,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        steps=[
            RunStep(
                id=uuid4(),
                run_id=run_id,
                name="ingest",
                status=RunStatus.SUCCESS,
                sequence=1,
                created_at=NOW,
            ),
            RunStep(
                id=uuid4(),
                run_id=run_id,
                name="transform",
                status=RunStatus.RUNNING,
                sequence=2,
                created_at=NOW,
            ),
        ],
    )


def test_run_round_trips(session: Session):
    pipeline_id = _seed_pipeline(session)
    repo = SqlAlchemyRunRepository(session)
    run = _make_run(pipeline_id)

    repo.add(run)
    session.commit()

    fetched = repo.get(run.id)
    assert fetched == run


def test_get_unknown_returns_none(session: Session):
    repo = SqlAlchemyRunRepository(session)
    assert repo.get(uuid4()) is None


def test_triggering_same_key_twice_persists_one_successful_execution(session: Session) -> None:
    pipeline_id = _seed_pipeline(session)
    runs = SqlAlchemyRunRepository(session)
    executor = SpyExecutor(runs)
    use_case = TriggerRun(runs=runs, executor=executor)

    key = RunKey(
        pipeline_id=pipeline_id,
        watermark="2026-07-06",
    )

    first = use_case.trigger(key, PLAN)
    second = use_case.trigger(key, PLAN)

    session.expire_all()

    success_count = session.execute(
        select(func.count())
        .select_from(RunRecord)
        .where(RunRecord.pipeline_id == pipeline_id)
        .where(RunRecord.watermark == "2026-07-06")
        .where(RunRecord.status == RunStatus.SUCCESS.value)
    ).scalar_one()

    assert first.executed is True
    assert second.executed is False
    assert second.run.id == first.run.id
    assert executor.calls == 1
    assert success_count == 1
