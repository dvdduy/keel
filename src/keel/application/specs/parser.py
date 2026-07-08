from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from keel.application.specs.diagnostics import (
    SpecError,
    SpecValidationError,
    diagnostics_from_validation_error,
)
from keel.application.specs.models import PipelineSpec


class SpecParseError(SpecError):
    """Raised when a pipeline spec cannot be parsed as YAML."""


def parse_pipeline_spec_yaml(content: str) -> PipelineSpec:
    """Parse a pipeline spec from YAML text."""

    raw_spec = yaml.safe_load(content)

    if raw_spec is None:
        raise SpecParseError("pipeline spec YAML is empty")

    if not isinstance(raw_spec, dict):
        raise SpecParseError("pipeline spec YAML must be a mapping/object")

    try:
        return PipelineSpec.model_validate(raw_spec)
    except ValidationError as err:
        raise SpecValidationError(diagnostics_from_validation_error(err)) from err


def parse_pipeline_spec_file(path: str | Path) -> PipelineSpec:
    """Parse a pipeline spec from a YAML file."""

    spec_path = Path(path)
    content = spec_path.read_text(encoding="utf-8")
    return parse_pipeline_spec_yaml(content)


def pipeline_spec_to_yaml(spec: PipelineSpec) -> str:
    """Serialize a pipeline spec back to YAML for round-trip tests."""

    data: dict[str, Any] = spec.model_dump(
        mode="json",
        exclude_none=True,
        exclude_defaults=True,
    )

    return yaml.safe_dump(data, sort_keys=False)
