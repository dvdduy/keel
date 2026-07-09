from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.adapters.db.models import QualityResultRecord
from keel.adapters.db.translators import (
    quality_result_to_record,
    record_to_quality_result,
)
from keel.application.quality.results import QualityResult


class SqlAlchemyQualityResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: QualityResult) -> None:
        self._session.add(quality_result_to_record(result))
        self._session.flush()

    def for_run(self, run_id: UUID) -> tuple[QualityResult, ...]:
        statement = (
            select(QualityResultRecord)
            .where(QualityResultRecord.run_id == run_id)
            .order_by(QualityResultRecord.created_at.asc())
        )
        records = self._session.execute(statement).scalars().all()
        return tuple(record_to_quality_result(record) for record in records)
