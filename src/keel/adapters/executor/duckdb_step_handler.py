from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from keel.application.execution.plan import IngestStep, PlanStep, TransformStep
from keel.application.ports.step_handler import Compensation
from keel.application.ports.transform import ModelResult, ModelStatus, TransformRunner
from keel.application.ports.warehouse import WarehouseAdapter


WarehouseFactory = Callable[[], WarehouseAdapter]


class TransformStepFailed(RuntimeError):
    """Raised when a transform model produced an interpretable failed result."""


@dataclass
class DuckDbStepHandler:
    warehouse_factory: WarehouseFactory
    transform_runner: TransformRunner

    def run(self, step: PlanStep) -> Compensation:
        match step:
            case IngestStep():
                return self._run_ingest(step)
            case TransformStep():
                return self._run_transform(step)
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
        result = self.transform_runner.run(step.model)

        if not result.ok:
            raise TransformStepFailed(_format_transform_failure(result.models))

        # dbt writes models to main.<model> in the Day 13 profile.
        return lambda: self._drop_relation(f"main.{step.model}")

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
