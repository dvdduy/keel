from pathlib import Path
from typing import Protocol


class WarehouseAdapter(Protocol):
    def ingest_csv(self, destination: str, source: Path) -> int:
        """Load `source` CSV into table `destination` (e.g. 'raw.orders'),
        replacing any existing table. Returns rows loaded"""
        ...

    def row_count(self, table: str) -> int: ...
