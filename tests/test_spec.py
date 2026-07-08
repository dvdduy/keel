from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from keel.application.specs.diagnostics import Diagnostic, SpecValidationError
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


def collect_diagnostics(spec: dict[str, Any]) -> tuple[Diagnostic, ...]:
    with pytest.raises(SpecValidationError) as exc_info:
        parse_spec_dict(spec)

    return exc_info.value.diagnostics


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


def test_parser_raises_spec_validation_error_not_pydantic() -> None:
    spec = load_valid_spec_dict()
    spec["owner"] = "duy"

    with pytest.raises(SpecValidationError) as exc_info:
        parse_spec_dict(spec)

    assert exc_info.type is SpecValidationError


def test_diagnostics_report_all_problems_at_once() -> None:
    spec = load_valid_spec_dict()
    spec["owner"] = "duy"
    spec["freshness"]["max_age_minutes"] = 0
    spec["typo_quality_checks"] = []

    diagnostics = collect_diagnostics(spec)

    assert len(diagnostics) == 3
    assert {diagnostic.loc for diagnostic in diagnostics} == {
        "freshness.max_age_minutes",
        "owner",
        "typo_quality_checks",
    }


def test_diagnostic_loc_renders_nested_path() -> None:
    spec = load_valid_spec_dict()
    spec["contract"][1]["name"] = "not a valid identifier"

    diagnostics = collect_diagnostics(spec)

    assert any(
        diagnostic.loc == "contract[1].name"
        and "contract column name must be a valid identifier" in diagnostic.message
        for diagnostic in diagnostics
    )


def test_diagnostic_messages_are_clean() -> None:
    spec = load_valid_spec_dict()
    spec["owner"] = "duy"
    spec["freshness"]["max_age_minutes"] = 0
    spec["typo_quality_checks"] = []

    with pytest.raises(SpecValidationError) as exc_info:
        parse_spec_dict(spec)

    report = str(exc_info.value)

    assert "https://errors.pydantic.dev" not in report
    assert "[type=" not in report
    assert "Value error," not in report


def test_pipeline_spec_rejects_unknown_top_level_key() -> None:
    spec = load_valid_spec_dict()
    spec["typo_quality_checks"] = []

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (Diagnostic("typo_quality_checks", "is not a supported field"),)


@pytest.mark.parametrize("max_age_minutes", [0, -1])
def test_pipeline_spec_rejects_non_positive_freshness(
    max_age_minutes: int,
) -> None:
    spec = load_valid_spec_dict()
    spec["freshness"]["max_age_minutes"] = max_age_minutes

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (Diagnostic("freshness.max_age_minutes", "must be greater than 0"),)


def test_pipeline_spec_rejects_duplicate_contract_columns() -> None:
    spec = load_valid_spec_dict()
    spec["contract"] = [
        {"name": "order_id", "type": "integer", "nullable": False},
        {"name": "order_id", "type": "decimal"},
    ]

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (Diagnostic("(root)", "contract column names must be unique"),)


def test_pipeline_spec_rejects_quality_check_for_unknown_column() -> None:
    spec = load_valid_spec_dict()
    spec["quality_checks"] = [
        {"type": "not_null", "column": "missing_column"},
    ]

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (
        Diagnostic(
            "(root)",
            "quality check references unknown column: missing_column",
        ),
    )


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

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (
        Diagnostic(
            "destination",
            "destination must use schema.table format, for example: raw.orders",
        ),
    )


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

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (Diagnostic("owner", "owner must be an email-like value"),)


def test_pipeline_spec_rejects_unknown_quality_check_type() -> None:
    spec = load_valid_spec_dict()
    spec["quality_checks"] = [
        {"type": "made_up_check", "column": "order_id"},
    ]

    diagnostics = collect_diagnostics(spec)

    assert diagnostics == (
        Diagnostic(
            "quality_checks[0].type",
            "has unsupported value 'made_up_check'",
        ),
    )


def test_unmapped_pydantic_messages_still_render_cleanly() -> None:
    spec = load_valid_spec_dict()
    spec["source"] = "csv"

    with pytest.raises(SpecValidationError) as exc_info:
        parse_spec_dict(spec)

    report = str(exc_info.value)

    assert "source:" in report
    assert "https://errors.pydantic.dev" not in report
    assert "[type=" not in report
    assert "Value error," not in report
