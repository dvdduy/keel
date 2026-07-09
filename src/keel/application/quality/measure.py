from __future__ import annotations

from keel.application.ports.warehouse import WarehouseAdapter, WarehouseError
from keel.application.quality.checks import ColumnMeasurement


def measure_column(
    *,
    warehouse: WarehouseAdapter,
    table: str,
    column: str,
) -> ColumnMeasurement | None:
    observed_schema = warehouse.describe_table(table)
    if observed_schema is None:
        return None

    if column not in {observed.name for observed in observed_schema.columns}:
        return None

    try:
        return ColumnMeasurement(
            row_count=warehouse.row_count(table),
            null_count=warehouse.null_count(table, column),
            distinct_count=warehouse.distinct_count(table, column),
        )
    except WarehouseError:
        return None
