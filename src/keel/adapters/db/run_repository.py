from uuid import UUID
from sqlalchemy.orm import Session
from keel.domain.run import Run
from keel.adapters.db.models import RunRecord
from keel.adapters.db.translators import run_to_record, record_to_run


class SqlAlchemyRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: Run) -> None:
        run_record = run_to_record(run)
        self._session.add(run_record)
        self._session.flush()

    def get(self, run_id: UUID) -> Run | None:
        run_record = self._session.get(RunRecord, run_id)
        return record_to_run(run_record) if run_record else None
