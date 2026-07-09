from __future__ import annotations

from keel.application.ports.warehouse import WarehouseAdapter
from keel.application.quality.checks import ColumnMeasurement


def measure_column(
    *,
    warehouse: WarehouseAdapter,
    table: str,
    column: str,
) -> ColumnMeasurement | None:
    """Gather facts a column check needs.

    Missing table or missing column is unobservable, so return None and let the
    pure evaluator produce UNKNOWN.
    """

    observed = warehouse.describe_table(table)
    if observed is None:
        return None

    observed_columns = {observed_column.name for observed_column in observed.columns}
    if column not in observed_columns:
        return None

    return ColumnMeasurement(
        row_count=warehouse.row_count(table),
        null_count=warehouse.null_count(table, column),
        distinct_count=warehouse.distinct_count(table, column),
    )
