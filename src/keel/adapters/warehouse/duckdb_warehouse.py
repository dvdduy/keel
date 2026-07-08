from __future__ import annotations

import duckdb

from pathlib import Path


class DuckDbWarehouse:
    """DuckDB-backed WarehouseAdapter.

    One adapter instance == one open connection to one DuckDB database
    (a file, or ':memory:').
    """

    def __init__(self, databasse: str) -> None:
        self._con = duckdb.connect(database=databasse)

    def ingest_csv(self, destination: str, source: Path) -> int:
        schema = self._schema_of(destination)
        if schema:
            self._con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

        self._con.execute(
            f"CREATE OR REPLACE TABLE {destination} AS " "SELECT * FROM read_csv_auto(?)",
            [str(source)],
        )

        return self.row_count(destination)

    def row_count(self, table: str) -> int:
        result = self._con.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert result is not None
        return int(result[0])

    @staticmethod
    def _schema_of(destination: str) -> str | None:
        schema, _, _table = destination.rpartition(".")
        return schema or None
