from pathlib import Path
from typing import Protocol
from datetime import datetime

from keel.application.reconcile.drift import ObservedSchema


class WarehouseError(RuntimeError):
    """Raised when warehouse state cannot be translated into Keel concepts."""


class WarehouseAdapter(Protocol):
    def ingest_csv(self, destination: str, source: Path) -> int:
        """Load `source` CSV into table `destination` (e.g. 'raw.orders'),
        replacing any existing table. Returns rows loaded"""
        ...

    def row_count(self, table: str) -> int: ...

    def drop_table(self, table: str) -> None:
        """Drop `table` if it exists."""
        ...

    def describe_table(self, table: str) -> ObservedSchema | None:
        """Observed schema of `table`, or None if the table does not exist.

        Warehouse-native physical types are translated to Keel ColumnType here.
        """
        ...

    def close(self) -> None:
        """Release any held warehouse resources."""
        ...

    def max_timestamp(self, table: str, column: str) -> datetime | None:
        """Return MAX(column) from table as a timezone-aware datetime.

        Returns None when the table is empty or all values are NULL.
        Raises WarehouseError when the table/column/type cannot be translated.
        """
        ...

    def null_count(self, table: str, column: str) -> int:
        """NULLs in column. Raises WarehouseError when unreadable."""
        ...

    def distinct_count(self, table: str, column: str) -> int:
        """Distinct NON-NULL values in column. Raises WarehouseError when unreadable."""
        ...
