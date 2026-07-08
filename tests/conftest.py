import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from keel.config import Settings
from uuid import UUID, uuid4
from datetime import datetime, timezone
from keel.adapters.db.models import TeamRecord, PipelineRecord

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    settings = Settings()
    engine = create_engine(settings.database_url, future=True)
    connection = engine.connect()
    trans = connection.begin()
    s = Session(connection)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def seeded_pipeline(session) -> UUID:
    team = TeamRecord(id=uuid4(), name="analytics", created_at=NOW)
    session.add(team)
    session.flush()
    pipeline = PipelineRecord(id=uuid4(), team_id=team.id, name="orders", created_at=NOW)
    session.add(pipeline)
    session.flush()
    return pipeline.id
