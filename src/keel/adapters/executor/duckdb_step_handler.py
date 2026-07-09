from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from keel.application.execution.plan import (
    IngestStep,
    PlanStep,
    QualityStep,
    TransformStep,
)
from keel.application.ports.quality_results import QualityResultRepository
from keel.application.ports.step_handler import Compensation
from keel.application.ports.transform import (
    ModelResult,
    ModelStatus,
    TestReport,
    TestStatus,
    TransformRunner,
)
from keel.application.ports.warehouse import WarehouseAdapter
from keel.application.quality.checks import evaluate_check
from keel.application.quality.gate import GateDecision, apply_gate
from keel.application.quality.measure import measure_column
from keel.application.specs.models import QualityCheckSpec

WarehouseFactory = Callable[[], WarehouseAdapter]


class TransformStepFailed(RuntimeError):
    """Raised when a transform step produced an interpretable failed result."""


class QualityGateFailed(RuntimeError):
    """Raised when a quality gate blocks the run."""


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class DuckDbStepHandler:
    warehouse_factory: WarehouseFactory
    transform_runner: TransformRunner
    results: QualityResultRepository | None = None
    clock: Callable[[], datetime] = _utc_now

    def run(self, step: PlanStep, *, run_id: UUID | None = None) -> Compensation:
        match step:
            case IngestStep():
                return self._run_ingest(step)
            case TransformStep():
                return self._run_transform(step)
            case QualityStep():
                if run_id is None:
                    raise QualityGateFailed("quality gate requires run context")
                return self._run_quality(step, run_id=run_id)
            case _:
                raise NotImplementedError(f"no DuckDB handler for step {step.key!r}")

    def _run_ingest(self, step: IngestStep) -> Compensation:
        warehouse = self.warehouse_factory()
        try:
            warehouse.ingest_csv(step.destination, Path(step.source_path))
        finally:
            warehouse.close()

        return lambda: self._drop_relation(step.destination)

    def _run_transform(self, step: TransformStep) -> Compensation:
        select = f"+{step.model}"
        result = self.transform_runner.run(select)
        if not result.ok:
            raise TransformStepFailed(_format_transform_failure(result.models))

        materialized_models = result.models

        test_report = self.transform_runner.test(select)
        if not test_report.ok:
            self._drop_materialized_models(materialized_models)
            raise TransformStepFailed(_format_test_failure(test_report))

        return lambda: self._drop_materialized_models(materialized_models)

    def _run_quality(self, step: QualityStep, *, run_id: UUID) -> Compensation:
        if self.results is None:
            raise QualityGateFailed("quality result repository is not configured")

        warehouse = self.warehouse_factory()
        try:
            measurement = measure_column(
                warehouse=warehouse,
                table=step.table,
                column=step.column,
            )
        finally:
            warehouse.close()

        result = evaluate_check(
            check=QualityCheckSpec(type=step.check, column=step.column),
            measurement=measurement,
        )

        decision = apply_gate(
            run_id=run_id,
            result=result,
            results=self.results,
            clock=self.clock,
        )

        if decision is GateDecision.BLOCK:
            raise QualityGateFailed(result.detail)

        return lambda: None

    def _drop_materialized_models(self, models: tuple[ModelResult, ...]) -> None:
        for model in reversed(models):
            self._drop_relation(f"main.{model.model}")

    def _drop_relation(self, relation: str) -> None:
        warehouse = self.warehouse_factory()
        try:
            warehouse.drop_table(relation)
        finally:
            warehouse.close()


def _format_transform_failure(models: tuple[ModelResult, ...]) -> str:
    failed = [model for model in models if model.status in {ModelStatus.ERROR, ModelStatus.SKIPPED}]
    if not failed:
        return "transform step failed"

    details = ", ".join(
        f"{model.model}={model.status.value}" + (f" ({model.message})" if model.message else "")
        for model in failed
    )
    return f"transform step failed: {details}"


def _format_test_failure(report: TestReport) -> str:
    failed = [test for test in report.tests if test.status in {TestStatus.FAIL, TestStatus.ERROR}]
    if not failed:
        return "transform test gate failed"

    details = ", ".join(
        f"{test.test}={test.status.value} failures={test.failures}"
        + (f" ({test.message})" if test.message else "")
        for test in failed
    )
    return f"transform test gate failed: {details}"
