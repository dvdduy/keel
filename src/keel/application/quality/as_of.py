from __future__ import annotations

from datetime import datetime

from keel.application.ports.warehouse import WarehouseAdapter
from keel.application.specs.models import PipelineSpec
from keel.domain.run import Run, RunStatus


def resolve_as_of(
    *,
    spec: PipelineSpec,
    warehouse: WarehouseAdapter,
    latest_successful_run: Run | None,
) -> datetime | None:
    """Resolve the timestamp used by freshness evaluation.

    Event-time watermark is primary. Wall-clock latest successful load is the
    explicit fallback for specs without a usable event-time column.

    The caller is responsible for finding latest_successful_run because the
    RunRepository port does not yet expose latest successful run by pipeline.
    """
    event_time_column = spec.freshness.event_time_column

    if event_time_column is not None:
        return warehouse.max_timestamp(spec.destination, event_time_column)

    if latest_successful_run is None:
        return None

    if latest_successful_run.status is not RunStatus.SUCCESS:
        return None

    return latest_successful_run.finished_at
