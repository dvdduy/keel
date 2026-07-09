from __future__ import annotations

import pytest

from keel.application.execution.plan import (
    ExecutionPlan,
    IngestStep,
    PlanValidationError,
    QualityStep,
    TransformStep,
)
from keel.application.execution.topology import topological_order
from keel.application.specs.models import QualityCheckType


def _keys(plan: ExecutionPlan) -> tuple[str, ...]:
    return tuple(step.key for step in topological_order(plan))


def test_linear_plan_orders_ingest_transform_quality() -> None:
    plan = ExecutionPlan(
        steps=(
            QualityStep(
                key="quality:not_null:order_id",
                depends_on=frozenset({"transform"}),
                check=QualityCheckType.NOT_NULL,
                column="order_id",
                table="main.stg_orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="stg_orders",
            ),
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path="data/orders.csv",
                destination="raw.orders",
            ),
        )
    )

    assert _keys(plan) == (
        "ingest",
        "transform",
        "quality:not_null:order_id",
    )


def test_fanout_quality_steps_ordered_after_last_data_step() -> None:
    plan = ExecutionPlan(
        steps=(
            QualityStep(
                key="quality:unique:order_id",
                depends_on=frozenset({"transform"}),
                check=QualityCheckType.UNIQUE,
                column="order_id",
                table="main.stg_orders",
            ),
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path="data/orders.csv",
                destination="raw.orders",
            ),
            QualityStep(
                key="quality:not_null:customer_id",
                depends_on=frozenset({"transform"}),
                check=QualityCheckType.NOT_NULL,
                column="customer_id",
                table="main.stg_orders",
            ),
            TransformStep(
                key="transform",
                depends_on=frozenset({"ingest"}),
                model="stg_orders",
            ),
        )
    )

    assert _keys(plan) == (
        "ingest",
        "transform",
        "quality:not_null:customer_id",
        "quality:unique:order_id",
    )


def test_ready_steps_broken_by_key_ascending() -> None:
    plan = ExecutionPlan(
        steps=(
            QualityStep(
                key="quality:z",
                depends_on=frozenset({"ingest"}),
                check=QualityCheckType.NOT_NULL,
                column="z",
                table="main.stg_orders",
            ),
            QualityStep(
                key="quality:a",
                depends_on=frozenset({"ingest"}),
                check=QualityCheckType.NOT_NULL,
                column="a",
                table="main.stg_orders",
            ),
            IngestStep(
                key="ingest",
                depends_on=frozenset(),
                source_path="data/orders.csv",
                destination="raw.orders",
            ),
        )
    )

    assert _keys(plan) == (
        "ingest",
        "quality:a",
        "quality:z",
    )


def test_cycle_raises_plan_validation_error() -> None:
    plan = ExecutionPlan(
        steps=(
            IngestStep(
                key="a",
                depends_on=frozenset({"c"}),
                source_path="data/orders.csv",
                destination="raw.orders",
            ),
            TransformStep(
                key="b",
                depends_on=frozenset({"a"}),
                model="stg_orders",
            ),
            QualityStep(
                key="c",
                depends_on=frozenset({"b"}),
                check=QualityCheckType.NOT_NULL,
                column="order_id",
                table="main.stg_orders",
            ),
        )
    )

    with pytest.raises(PlanValidationError, match="a, b, c"):
        topological_order(plan)
