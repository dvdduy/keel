from __future__ import annotations

from datetime import datetime, timezone

import pytest

from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.ports.warehouse import WarehouseError


def test_max_timestamp_returns_latest_timestamp_as_timezone_aware_utc() -> None:
    warehouse = DuckDbWarehouse(":memory:")

    try:
        warehouse._con.execute("CREATE SCHEMA raw")
        warehouse._con.execute(
            """
            CREATE TABLE raw.orders (
                order_id INTEGER,
                order_created_at TIMESTAMP
            )
            """
        )
        warehouse._con.execute(
            """
            INSERT INTO raw.orders VALUES
                (1, TIMESTAMP '2026-07-08 10:00:00'),
                (2, TIMESTAMP '2026-07-08 12:30:00'),
                (3, TIMESTAMP '2026-07-08 11:00:00')
            """
        )

        result = warehouse.max_timestamp("raw.orders", "order_created_at")

        assert result == datetime(2026, 7, 8, 12, 30, tzinfo=timezone.utc)
    finally:
        warehouse.close()


def test_max_timestamp_returns_none_for_empty_table() -> None:
    warehouse = DuckDbWarehouse(":memory:")

    try:
        warehouse._con.execute("CREATE SCHEMA raw")
        warehouse._con.execute(
            """
            CREATE TABLE raw.orders (
                order_id INTEGER,
                order_created_at TIMESTAMP
            )
            """
        )

        result = warehouse.max_timestamp("raw.orders", "order_created_at")

        assert result is None
    finally:
        warehouse.close()


def test_max_timestamp_rejects_non_timestamp_column() -> None:
    warehouse = DuckDbWarehouse(":memory:")

    try:
        warehouse._con.execute("CREATE SCHEMA raw")
        warehouse._con.execute(
            """
            CREATE TABLE raw.orders (
                order_id INTEGER,
                amount DECIMAL(18, 2)
            )
            """
        )
        warehouse._con.execute("INSERT INTO raw.orders VALUES (1, 12.34)")

        with pytest.raises(WarehouseError, match="non-timestamp value"):
            warehouse.max_timestamp("raw.orders", "amount")
    finally:
        warehouse.close()


def test_max_timestamp_wraps_missing_column_as_warehouse_error() -> None:
    warehouse = DuckDbWarehouse(":memory:")

    try:
        warehouse._con.execute("CREATE SCHEMA raw")
        warehouse._con.execute(
            """
            CREATE TABLE raw.orders (
                order_id INTEGER,
                order_created_at TIMESTAMP
            )
            """
        )

        with pytest.raises(WarehouseError, match="failed to read max timestamp"):
            warehouse.max_timestamp("raw.orders", "missing_created_at")
    finally:
        warehouse.close()
