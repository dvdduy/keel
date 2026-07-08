from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from keel.adapters.db.models import SpecVersionRecord
from keel.application.specs.versioning import SpecVersion


def spec_version_to_record(version: SpecVersion) -> SpecVersionRecord:
    return SpecVersionRecord(
        version_id=version.version_id,
        pipeline_id=version.pipeline_id,
        spec_id=version.spec_id,
        parent_id=version.parent_id,
        content=version.content,
        created_at=version.created_at,
    )


def record_to_spec_version(record: SpecVersionRecord) -> SpecVersion:
    return SpecVersion(
        version_id=record.version_id,
        pipeline_id=record.pipeline_id,
        spec_id=record.spec_id,
        parent_id=record.parent_id,
        content=record.content,
        created_at=record.created_at,
    )


class SqlAlchemySpecVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, version: SpecVersion) -> None:
        self._session.add(spec_version_to_record(version))
        self._session.flush()

    def head_for(self, pipeline_id: UUID) -> SpecVersion | None:
        stmt = (
            select(SpecVersionRecord)
            .where(SpecVersionRecord.pipeline_id == pipeline_id)
            .order_by(desc(SpecVersionRecord.seq))
            .limit(1)
        )
        record = self._session.execute(stmt).scalar_one_or_none()
        return None if record is None else record_to_spec_version(record)
