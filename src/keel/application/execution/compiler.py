from __future__ import annotations

from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanStep,
    QualityStep,
    StepKind,
    TransformStep,
)
from keel.application.specs.models import PipelineSpec


def compile_plan(spec: PipelineSpec) -> ExecutionPlan:
    """Compile a declarative PipelineSpec into a deterministic execution DAG"""

    steps: list[PlanStep] = [
        IngestStep(
            key="ingest",
            depends_on=frozenset(),
            source_path=spec.source.path,
            destination=spec.destination,
        )
    ]

    last_data_step_key = StepKind.INGEST.value

    if spec.transform is not None:
        steps.append(
            TransformStep(key="transform", depends_on=frozenset({"ingest"}), model=spec.transform)
        )
        last_data_step_key = StepKind.TRANSFORM.value

    for check in spec.quality_checks:
        steps.append(
            QualityStep(
                key=f"{StepKind.QUALITY_CHECK.value}:{check.type.value}:{check.column}",
                depends_on=frozenset({last_data_step_key}),
                check=check.type,
                column=check.column,
                table=(
                    f"main.{spec.transform}" if spec.transform is not None else spec.destination
                ),
            )
        )

    return ExecutionPlan(steps=tuple(steps))
