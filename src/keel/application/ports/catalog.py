from __future__ import annotations

from typing import Protocol

from keel.application.catalog.entry import CatalogEntry


class DatasetCatalog(Protocol):
    def upsert(self, entry: CatalogEntry) -> None: ...

    def get(self, dataset: str) -> CatalogEntry | None: ...

    def list(self) -> tuple[CatalogEntry, ...]: ...
