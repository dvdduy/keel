from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol


class TransformError(RuntimeError):
    """Transform tooling failed to produce interpretable results."""


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


class TestStatus(StrEnum):
    __test__: ClassVar[bool] = False

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    WARN = "warn"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TestResult:
    __test__: ClassVar[bool] = False

    test: str
    status: TestStatus
    failures: int
    message: str | None


@dataclass(frozen=True)
class TestReport:
    __test__: ClassVar[bool] = False

    ok: bool
    tests: tuple[TestResult, ...]


@dataclass(frozen=True)
class ManifestNode:
    unique_id: str
    resource_type: str
    name: str
    depends_on: frozenset[str]


@dataclass(frozen=True)
class TransformManifest:
    nodes: tuple[ManifestNode, ...]


class TransformRunner(Protocol):
    def run(self, select: str) -> TransformResult:
        """Run selected models and return per-model results.

        Raise TransformError only when the transform tool fails before producing
        interpretable model results. A model SQL failure is a TransformResult.
        """
        ...

    def test(self, select: str) -> TestReport:
        """Run tests for selected models and return per-test results.

        Raise TransformError only when the transform tool fails before producing
        interpretable test results. A dbt test failure is a TestReport.
        """
        ...

    def capture_manifest(self) -> TransformManifest:
        """Read the latest transform manifest artifact without invoking the tool."""
        ...
