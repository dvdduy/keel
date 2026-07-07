import pytest
from pydantic import ValidationError

from keel.config import Settings


def test_missing_database_url_fails_fast(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/db"
