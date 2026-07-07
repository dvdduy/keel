import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from keel.config import Settings


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
