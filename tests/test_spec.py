from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from keel.application.specs.models import QualityCheckType
from keel.application.specs.parser import (
    SpecParseError,
    parse_pipeline_spec_file,
    parse_pipeline_spec_yaml,
    pipeline_spec_to_yaml,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ORDERS_RAW_FIXTURE = FIXTURES_DIR / "orders_raw.yaml"


def load_valid_spec_dict() -> dict[str, Any]:
    loaded = yaml.safe_load(ORDERS_RAW_FIXTURE.read_text(encoding="utf-8"))

    assert isinstance(loaded, dict)

    return loaded


def parse_spec_dict(spec: dict[str, Any]):
    yaml_content = yaml.safe_dump(spec, sort_keys=False)

    return parse_pipeline_spec_yaml(yaml_content)


def test_parse_pipeline_spec_file() -> None:
    spec = parse_pipeline_spec_file(ORDERS_RAW_FIXTURE)

    assert spec.name == "orders_raw"
    assert spec.team == "growth"
    assert spec.owner == "duy@keel.dev"
    assert spec.source.type == "csv"
    assert spec.source.path == "seeds/orders.csv"
    assert spec.destination == "raw.orders"
    assert spec.contract[0].name == "order_id"
    assert spec.contract[0].nullable is False
    assert spec.contract[1].nullable is True
    assert spec.transform == "stg_orders"
    assert spec.freshness.max_age_minutes == 60
    assert spec.quality_checks[0].type == QualityCheckType.NOT_NULL
    assert spec.quality_checks[1].type == QualityCheckType.UNIQUE


def test_pipeline_spec_round_trips_through_yaml() -> None:
    spec = parse_pipeline_spec_file(ORDERS_RAW_FIXTURE)

    dumped = pipeline_spec_to_yaml(spec)
    reparsed = parse_pipeline_spec_yaml(dumped)

    assert reparsed == spec


def test_pipeline_spec_to_yaml_dumps_enum_values_as_json_scalars() -> None:
    spec = parse_pipeline_spec_file(ORDERS_RAW_FIXTURE)

    dumped = pipeline_spec_to_yaml(spec)
    data = yaml.safe_load(dumped)

    assert data["source"]["type"] == "csv"
    assert data["contract"][0]["type"] == "integer"
    assert data["quality_checks"][0]["type"] == "not_null"
    assert data["quality_checks"][1]["type"] == "unique"


def test_parse_pipeline_spec_yaml_rejects_empty_yaml() -> None:
    with pytest.raises(SpecParseError, match="empty"):
        parse_pipeline_spec_yaml("")


def test_parse_pipeline_spec_yaml_rejects_non_mapping_yaml() -> None:
    yaml_content = """
- orders_raw
- growth
"""

    with pytest.raises(SpecParseError, match="mapping/object"):
        parse_pipeline_spec_yaml(yaml_content)


def test_pipeline_spec_rejects_unknown_top_level_key() -> None:
    spec = load_valid_spec_dict()
    spec["typo_quality_checks"] = []

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_spec_dict(spec)


@pytest.mark.parametrize("max_age_minutes", [0, -1])
def test_pipeline_spec_rejects_non_positive_freshness(max_age_minutes: int) -> None:
    spec = load_valid_spec_dict()
    spec["freshness"]["max_age_minutes"] = max_age_minutes

    with pytest.raises(ValidationError, match="greater than 0"):
        parse_spec_dict(spec)


def test_pipeline_spec_rejects_duplicate_contract_columns() -> None:
    spec = load_valid_spec_dict()
    spec["contract"] = [
        {"name": "order_id", "type": "integer", "nullable": False},
        {"name": "order_id", "type": "decimal"},
    ]

    with pytest.raises(ValidationError, match="contract column names must be unique"):
        parse_spec_dict(spec)


def test_pipeline_spec_rejects_quality_check_for_unknown_column() -> None:
    spec = load_valid_spec_dict()
    spec["quality_checks"] = [
        {"type": "not_null", "column": "missing_column"},
    ]

    with pytest.raises(
        ValidationError,
        match="quality check references unknown column: missing_column",
    ):
        parse_spec_dict(spec)


@pytest.mark.parametrize(
    "destination",
    [
        "orders",
        "raw.",
        ".orders",
        "raw.orders.v2",
        "raw-orders.orders",
    ],
)
def test_pipeline_spec_rejects_invalid_destination(destination: str) -> None:
    spec = load_valid_spec_dict()
    spec["destination"] = destination

    with pytest.raises(ValidationError, match="schema.table"):
        parse_spec_dict(spec)


@pytest.mark.parametrize(
    "owner",
    [
        "duy",
        "@keel.dev",
        "duy@",
    ],
)
def test_pipeline_spec_rejects_invalid_owner(owner: str) -> None:
    spec = load_valid_spec_dict()
    spec["owner"] = owner

    with pytest.raises(ValidationError, match="owner must be an email-like value"):
        parse_spec_dict(spec)


def test_pipeline_spec_rejects_unknown_quality_check_type() -> None:
    spec = load_valid_spec_dict()
    spec["quality_checks"] = [
        {"type": "made_up_check", "column": "order_id"},
    ]

    with pytest.raises(ValidationError, match="made_up_check"):
        parse_spec_dict(spec)
