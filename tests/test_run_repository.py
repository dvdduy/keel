from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from keel.adapters.db.models import PipelineRecord, TeamRecord
from keel.adapters.db.run_repository import SqlAlchemyRunRepository
from keel.domain.run import Run, RunStatus, RunStep

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


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
