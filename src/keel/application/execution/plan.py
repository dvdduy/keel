from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from keel.application.specs.models import QualityCheckSpec


class PlanValidationError(Exception):
    """Raised when an execution plan violates DAG invariants."""


class StepKind(StrEnum):
    INGEST = "ingest"
    TRANSFORM = "transform"
    QUALITY_CHECK = "quality"


@dataclass(frozen=True)
class IngestStep:
    key: str
    depends_on: frozenset[str]
    source_path: str
    destination: str


@dataclass(frozen=True)
class TransformStep:
    key: str
    depends_on: frozenset[str]
    model: str


@dataclass(frozen=True)
class QualityGateStep:
    key: str
    depends_on: frozenset[str]
    table: str
    checks: tuple[QualityCheckSpec, ...]


PlanStep = IngestStep | TransformStep | QualityGateStep


@dataclass(frozen=True)
class ExecutionPlan:
    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        step_keys = [step.key for step in self.steps]
        known_keys = set(step_keys)

        duplicate_keys = sorted(key for key in known_keys if step_keys.count(key) > 1)

        if duplicate_keys:
            raise PlanValidationError(
                "execution plan contains duplicate step keys: " + ", ".join(duplicate_keys)
            )

        dangling_dependencies = sorted(
            {
                dependency
                for step in self.steps
                for dependency in step.depends_on
                if dependency not in known_keys
            }
        )

        if dangling_dependencies:
            raise PlanValidationError(
                "execution plan contains dangling dependencies: " + ", ".join(dangling_dependencies)
            )
