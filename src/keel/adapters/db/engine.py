from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from keel.config import Settings


def make_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_engine(settings.database_url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)
