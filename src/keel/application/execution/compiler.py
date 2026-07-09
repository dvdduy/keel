from __future__ import annotations

from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanStep,
    QualityGateStep,
    StepKind,
    TransformStep,
)
from keel.application.specs.models import PipelineSpec


def compile_plan(spec: PipelineSpec) -> ExecutionPlan:
    """Compile a declarative PipelineSpec into a deterministic execution DAG."""

    steps: list[PlanStep] = [
        IngestStep(
            key=StepKind.INGEST.value,
            depends_on=frozenset(),
            source_path=spec.source.path,
            destination=spec.destination,
        )
    ]

    last_data_step_key = StepKind.INGEST.value
    quality_table = spec.destination

    if spec.transform is not None:
        steps.append(
            TransformStep(
                key=StepKind.TRANSFORM.value,
                depends_on=frozenset({StepKind.INGEST.value}),
                model=spec.transform,
            )
        )
        last_data_step_key = StepKind.TRANSFORM.value
        quality_table = f"main.{spec.transform}"

    if spec.quality_checks:
        steps.append(
            QualityGateStep(
                key=StepKind.QUALITY_CHECK.value,
                depends_on=frozenset({last_data_step_key}),
                table=quality_table,
                checks=tuple(spec.quality_checks),
            )
        )

    return ExecutionPlan(steps=tuple(steps))
