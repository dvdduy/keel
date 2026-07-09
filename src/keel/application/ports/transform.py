from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class TransformError(RuntimeError):
    """Transform tooling failed to produce interpretable model results."""


class ModelStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ModelResult:
    model: str
    status: ModelStatus
    message: str | None


@dataclass(frozen=True)
class TransformResult:
    ok: bool
    models: tuple[ModelResult, ...]


class TransformRunner(Protocol):
    def run(self, select: str) -> TransformResult:
        """Run selected models and return per-model results.

        Raise TransformError only when the transform tool fails before producing
        interpretable model results. A model SQL failure is a TransformResult.
        """
        ...
