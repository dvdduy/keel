from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from keel.application.quality.as_of import resolve_as_of
from keel.application.reconcile.drift import ObservedSchema
from keel.application.specs.models import PipelineSpec
from keel.domain.run import Run, RunStatus


class FakeWarehouse:
    def __init__(self, max_timestamp: datetime | None) -> None:
        self.max_timestamp_value = max_timestamp
        self.calls: list[tuple[str, str]] = []

    def ingest_csv(self, destination: str, source: Path) -> int:
        raise NotImplementedError

    def row_count(self, table: str) -> int:
        raise NotImplementedError

    def drop_table(self, table: str) -> None:
        raise NotImplementedError

    def describe_table(self, table: str) -> ObservedSchema | None:
        raise NotImplementedError

    def max_timestamp(self, table: str, column: str) -> datetime | None:
        self.calls.append((table, column))
        return self.max_timestamp_value

    def close(self) -> None:
        raise NotImplementedError


def _spec(*, event_time_column: str | None) -> PipelineSpec:
    raw_spec: dict[str, object] = {
        "name": "orders",
        "team": "analytics",
        "owner": "data@example.com",
        "source": {"type": "csv", "path": "orders.csv"},
        "destination": "raw.orders",
        "contract": [
            {"name": "order_id", "type": "integer", "nullable": False},
            {"name": "order_created_at", "type": "timestamp", "nullable": False},
        ],
        "freshness": {"max_age_minutes": 60},
        "quality_checks": [],
    }

    if event_time_column is not None:
        raw_spec["freshness"] = {
            "max_age_minutes": 60,
            "event_time_column": event_time_column,
        }

    return PipelineSpec.model_validate(raw_spec)


def test_resolve_as_of_uses_event_time_watermark_when_declared() -> None:
    watermark = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    warehouse = FakeWarehouse(max_timestamp=watermark)

    result = resolve_as_of(
        spec=_spec(event_time_column="order_created_at"),
        warehouse=warehouse,
        latest_successful_run=None,
    )

    assert result == watermark
    assert warehouse.calls == [("raw.orders", "order_created_at")]


def test_resolve_as_of_returns_none_when_event_time_table_is_empty() -> None:
    warehouse = FakeWarehouse(max_timestamp=None)

    result = resolve_as_of(
        spec=_spec(event_time_column="order_created_at"),
        warehouse=warehouse,
        latest_successful_run=None,
    )

    assert result is None
    assert warehouse.calls == [("raw.orders", "order_created_at")]


def test_resolve_as_of_falls_back_to_latest_successful_run_finished_at() -> None:
    finished_at = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    run = Run(
        id=uuid4(),
        pipeline_id=uuid4(),
        created_at=datetime(2026, 7, 8, 11, 55, tzinfo=timezone.utc),
        status=RunStatus.SUCCESS,
        finished_at=finished_at,
    )

    warehouse = FakeWarehouse(max_timestamp=None)

    result = resolve_as_of(
        spec=_spec(event_time_column=None),
        warehouse=warehouse,
        latest_successful_run=run,
    )

    assert result == finished_at
    assert warehouse.calls == []


def test_resolve_as_of_returns_none_without_event_time_or_successful_run() -> None:
    warehouse = FakeWarehouse(max_timestamp=None)

    result = resolve_as_of(
        spec=_spec(event_time_column=None),
        warehouse=warehouse,
        latest_successful_run=None,
    )

    assert result is None
    assert warehouse.calls == []


def test_resolve_as_of_ignores_non_successful_fallback_run() -> None:
    run = Run(
        id=uuid4(),
        pipeline_id=uuid4(),
        created_at=datetime(2026, 7, 8, 11, 55, tzinfo=timezone.utc),
        status=RunStatus.FAILED,
        finished_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
    )

    warehouse = FakeWarehouse(max_timestamp=None)

    result = resolve_as_of(
        spec=_spec(event_time_column=None),
        warehouse=warehouse,
        latest_successful_run=run,
    )

    assert result is None
    assert warehouse.calls == []
