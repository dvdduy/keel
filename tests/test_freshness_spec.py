from __future__ import annotations

import pytest
from pydantic import ValidationError

from keel.application.specs.models import PipelineSpec


def _valid_spec_dict() -> dict[str, object]:
    return {
        "name": "orders",
        "team": "analytics",
        "owner": "data@example.com",
        "source": {"type": "csv", "path": "orders.csv"},
        "destination": "raw.orders",
        "contract": [
            {"name": "order_id", "type": "integer", "nullable": False},
            {"name": "order_created_at", "type": "timestamp", "nullable": False},
            {"name": "amount", "type": "decimal", "nullable": False},
        ],
        "freshness": {
            "max_age_minutes": 60,
            "event_time_column": "order_created_at",
        },
        "quality_checks": [],
    }


def test_freshness_event_time_column_is_parsed() -> None:
    spec = PipelineSpec.model_validate(_valid_spec_dict())

    assert spec.freshness.event_time_column == "order_created_at"


def test_freshness_event_time_column_must_reference_contract_column() -> None:
    raw_spec = _valid_spec_dict()
    raw_spec["freshness"] = {
        "max_age_minutes": 60,
        "event_time_column": "missing_created_at",
    }

    with pytest.raises(ValidationError, match="references unknown column"):
        PipelineSpec.model_validate(raw_spec)


def test_freshness_event_time_column_must_reference_timestamp_column() -> None:
    raw_spec = _valid_spec_dict()
    raw_spec["freshness"] = {
        "max_age_minutes": 60,
        "event_time_column": "amount",
    }

    with pytest.raises(ValidationError, match="must reference a timestamp column"):
        PipelineSpec.model_validate(raw_spec)


def test_freshness_event_time_column_must_be_identifier() -> None:
    raw_spec = _valid_spec_dict()
    raw_spec["freshness"] = {
        "max_age_minutes": 60,
        "event_time_column": "order-created-at",
    }

    with pytest.raises(ValidationError, match="must be a valid identifier"):
        PipelineSpec.model_validate(raw_spec)
