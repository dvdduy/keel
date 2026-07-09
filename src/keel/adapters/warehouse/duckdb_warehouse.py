from __future__ import annotations

import duckdb

from pathlib import Path

from keel.application.ports.warehouse import WarehouseError
from keel.application.reconcile.drift import ObservedColumn, ObservedSchema
from keel.application.specs.models import ColumnType


class DuckDbWarehouse:
    """DuckDB-backed WarehouseAdapter.

    One adapter instance == one open connection to one DuckDB database
    (a file, or ':memory:').
    """

    def __init__(self, database: str) -> None:
        self._con = duckdb.connect(database=database)

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

    def drop_table(self, table: str) -> None:
        try:
            self._con.execute(f"DROP TABLE IF EXISTS {table}")
        except duckdb.Error as exc:
            raise WarehouseError(f"failed to drop DuckDB table {table!r}") from exc

    def describe_table(self, table: str) -> ObservedSchema | None:
        try:
            rows = self._con.execute(f"DESCRIBE {table}").fetchall()
        except duckdb.CatalogException:
            return None

        return ObservedSchema(
            columns=tuple(
                ObservedColumn(
                    name=str(row[0]),
                    type=self._to_column_type(str(row[1])),
                )
                for row in rows
            )
        )

    def close(self) -> None:
        self._con.close()

    @staticmethod
    def _to_column_type(physical_type: str) -> ColumnType:
        normalized = physical_type.upper()

        if normalized in {"INTEGER", "BIGINT"}:
            return ColumnType.INTEGER

        if normalized.startswith("DECIMAL"):
            return ColumnType.DECIMAL

        if normalized in {"DOUBLE", "FLOAT", "REAL"}:
            return ColumnType.DECIMAL

        if normalized in {"VARCHAR", "TEXT"}:
            return ColumnType.STRING

        if normalized.startswith("TIMESTAMP"):
            return ColumnType.TIMESTAMP

        if normalized == "BOOLEAN":
            return ColumnType.BOOLEAN

        raise WarehouseError(f"unsupported DuckDB column type: {physical_type}")

    @staticmethod
    def _schema_of(destination: str) -> str | None:
        schema, _, _table = destination.rpartition(".")
        return schema or None
