from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from keel.adapters.db.models import DatasetRecord
from keel.adapters.db.translators import catalog_entry_to_record, record_to_catalog_entry
from keel.application.catalog.entry import CatalogEntry


class SqlAlchemyDatasetCatalog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, entry: CatalogEntry) -> None:
        self._session.merge(catalog_entry_to_record(entry))
        self._session.flush()

    def get(self, dataset: str) -> CatalogEntry | None:
        record = self._session.get(DatasetRecord, dataset)
        return None if record is None else record_to_catalog_entry(record)

    def list(self) -> tuple[CatalogEntry, ...]:
        records = self._session.scalars(select(DatasetRecord).order_by(DatasetRecord.dataset)).all()
        return tuple(record_to_catalog_entry(record) for record in records)
