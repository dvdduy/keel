from pathlib import Path
from typing import Protocol

from keel.application.reconcile.drift import ObservedSchema


class WarehouseError(RuntimeError):
    """Raised when warehouse state cannot be translated into Keel concepts."""


class WarehouseAdapter(Protocol):
    def ingest_csv(self, destination: str, source: Path) -> int:
        """Load `source` CSV into table `destination` (e.g. 'raw.orders'),
        replacing any existing table. Returns rows loaded"""
        ...

    def row_count(self, table: str) -> int: ...

    def describe_table(self, table: str) -> ObservedSchema | None:
        """Observed schema of `table`, or None if the table does not exist.

        Warehouse-native physical types are translated to Keel ColumnType here.
        """
        ...
