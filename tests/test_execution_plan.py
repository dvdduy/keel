from __future__ import annotations

import pytest

from keel.application.execution.compiler import compile_plan
from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanValidationError,
    QualityGateStep,
    TransformStep,
)
from keel.application.specs.models import (
    ContractColumn,
    FreshnessSpec,
    PipelineSpec,
    SourceSpec,
    SourceType,
    QualityCheckSpec,
    QualityCheckType,
)


def make_spec(
    *,
    transform: str | None = None,
    quality_checks: list[QualityCheckSpec] | None = None,
) -> PipelineSpec:
    return PipelineSpec(
        name="orders",
        team="analytics",
        owner="data-platform@example.com",
        source=SourceSpec(
            type=SourceType.CSV,
            path="data/orders.csv",
        ),
        destination="raw.orders",
        contract=[
            ContractColumn(name="order_id", type="string", nullable=False),
            ContractColumn(name="customer_id", type="string", nullable=True),
        ],
        freshness=FreshnessSpec(max_age_minutes=60),
        transform=transform,
        quality_checks=quality_checks or [],
    )


def test_minimal_spec_compiles_to_single_ingest_step() -> None:
    spec = make_spec()

    plan = compile_plan(spec)

    assert len(plan.steps) == 1

    step = plan.steps[0]
    assert isinstance(step, IngestStep)
    assert step.key == "ingest"
    assert step.depends_on == frozenset()


def test_ingest_step_carries_source_and_destination() -> None:
    spec = make_spec()

    plan = compile_plan(spec)

    step = plan.steps[0]
    assert isinstance(step, IngestStep)
    assert step.source_path == "data/orders.csv"
    assert step.destination == "raw.orders"


def test_transform_step_depends_on_ingest() -> None:
    spec = make_spec(transform="stg_orders")

    plan = compile_plan(spec)

    step = plan.steps[1]
    assert isinstance(step, TransformStep)
    assert step.key == "transform"
    assert step.depends_on == frozenset({"ingest"})
    assert step.model == "stg_orders"


def test_quality_checks_depend_on_ingest_without_transform() -> None:
    spec = make_spec(
        quality_checks=[QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id")]
    )

    plan = compile_plan(spec)

    step = plan.steps[1]
    assert isinstance(step, QualityGateStep)
    assert step.depends_on == frozenset({"ingest"})


def test_quality_checks_depend_on_transform_when_present() -> None:
    spec = make_spec(
        transform="stg_orders",
        quality_checks=[QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id")],
    )

    plan = compile_plan(spec)

    step = plan.steps[2]
    assert isinstance(step, QualityGateStep)
    assert step.depends_on == frozenset({"transform"})


def test_compilation_is_deterministic() -> None:
    spec = make_spec(
        transform="stg_orders",
        quality_checks=[QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id")],
    )

    assert compile_plan(spec) == compile_plan(spec)


def test_plan_rejects_dangling_dependency() -> None:
    with pytest.raises(PlanValidationError):
        ExecutionPlan(
            steps=(
                TransformStep(
                    key="transform",
                    depends_on=frozenset({"missing"}),
                    model="stg_orders",
                ),
            )
        )


def test_plan_rejects_duplicate_step_keys() -> None:
    with pytest.raises(PlanValidationError):
        ExecutionPlan(
            steps=(
                IngestStep(
                    key="ingest",
                    depends_on=frozenset(),
                    source_path="data/orders.csv",
                    destination="raw.orders",
                ),
                IngestStep(
                    key="ingest",
                    depends_on=frozenset(),
                    source_path="data/customers.csv",
                    destination="raw.customers",
                ),
            )
        )


def test_compiler_emits_one_quality_gate_for_multiple_checks() -> None:
    spec = make_spec(
        quality_checks=[
            QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id"),
            QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="customer_id"),
        ]
    )

    plan = compile_plan(spec)

    quality_steps = [step for step in plan.steps if isinstance(step, QualityGateStep)]

    assert len(quality_steps) == 1
    assert quality_steps[0].key == "quality"
    assert quality_steps[0].depends_on == frozenset({"ingest"})
    assert quality_steps[0].table == "raw.orders"
    assert quality_steps[0].checks == spec.quality_checks


def test_quality_gate_carries_table_and_checks() -> None:
    checks = [
        QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id"),
    ]
    spec = make_spec(quality_checks=checks)

    plan = compile_plan(spec)

    step = plan.steps[1]

    assert isinstance(step, QualityGateStep)
    assert step.key == "quality"
    assert step.table == "raw.orders"
    assert step.checks == tuple(checks)


def test_plan_preserves_quality_check_order_inside_gate() -> None:
    checks = [
        QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="order_id"),
        QualityCheckSpec(type=QualityCheckType.NOT_NULL, column="customer_id"),
    ]
    spec = make_spec(quality_checks=checks)

    plan = compile_plan(spec)

    assert [step.key for step in plan.steps] == ["ingest", "quality"]

    step = plan.steps[1]
    assert isinstance(step, QualityGateStep)
    assert step.checks == tuple(checks)
