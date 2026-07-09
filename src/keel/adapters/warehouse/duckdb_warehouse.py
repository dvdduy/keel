from __future__ import annotations

import duckdb

import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from keel.application.ports.warehouse import WarehouseError
from keel.application.reconcile.drift import ObservedColumn, ObservedSchema
from keel.application.specs.models import ColumnType

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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

    def max_timestamp(self, table: str, column: str) -> datetime | None:
        table_sql = _quote_qualified_identifier(table)
        column_sql = _quote_identifier(column)

        try:
            row = self._con.execute(f"SELECT MAX({column_sql}) FROM {table_sql}").fetchone()
        except duckdb.CatalogException as exc:
            raise WarehouseError(f"failed to read max timestamp from {table!r}.{column!r}") from exc
        except duckdb.BinderException as exc:
            raise WarehouseError(f"failed to read max timestamp from {table!r}.{column!r}") from exc
        except duckdb.Error as exc:
            raise WarehouseError(f"failed to read max timestamp from {table!r}.{column!r}") from exc

        if row is None or row[0] is None:
            return None

        value: Any = row[0]
        if not isinstance(value, datetime):
            raise WarehouseError(
                f"MAX({column}) from {table!r} returned non-timestamp value: "
                f"{type(value).__name__}"
            )

        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

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


def _quote_qualified_identifier(value: str) -> str:
    parts = value.split(".")
    if not parts:
        raise WarehouseError("warehouse identifier must not be empty")

    return ".".join(_quote_identifier(part) for part in parts)


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise WarehouseError(f"invalid warehouse identifier: {value!r}")

    return f'"{value}"'
