from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select

from keel.adapters.db.models import PipelineRecord, SpecVersionRecord, TeamRecord
from keel.adapters.db.spec_version_repository import SqlAlchemySpecVersionRepository
from keel.application.lineage.edges import build_lineage_graph
from keel.application.specs.models import ColumnType, ContractColumn, PipelineSpec
from keel.application.specs.parser import parse_pipeline_spec_yaml
from keel.application.use_cases.submit_spec import SubmitSpec
from keel.application.specs.versioning import SpecVersion


def _pipeline_id(seeded_pipeline) -> UUID:
    return seeded_pipeline if isinstance(seeded_pipeline, UUID) else seeded_pipeline.id


def _spec(
    destination: str = "analytics.orders",
    *,
    source_path: str = "tests/fixtures/orders.csv",
    transform: str | None = None,
):
    transform_line = f"transform: {transform}\n" if transform is not None else ""
    return parse_pipeline_spec_yaml(
        f"""name: orders_daily
team: analytics
owner: data-platform@example.com
source:
  type: csv
  path: {source_path}
contract:
  - name: order_id
    type: string
  - name: amount
    type: decimal
destination: {destination}
{transform_line}freshness:
  max_age_minutes: 60
quality_checks: []
"""
    )


def _dropped_amount_spec() -> PipelineSpec:
    spec = _spec()
    return spec.model_copy(
        update={
            "contract": (
                ContractColumn(
                    name="order_id",
                    type=ColumnType.STRING,
                    nullable=True,
                ),
            )
        }
    )


def test_submit_identical_twice_persists_one_row(session, seeded_pipeline) -> None:
    pipeline_id = _pipeline_id(seeded_pipeline)
    submit = SubmitSpec(SqlAlchemySpecVersionRepository(session))
    spec = _spec()

    first = submit.submit(pipeline_id, spec)
    second = submit.submit(pipeline_id, spec)

    row_count = session.execute(select(func.count()).select_from(SpecVersionRecord)).scalar_one()

    assert first.created is True
    assert second.created is False
    assert second.version.version_id == first.version.version_id
    assert row_count == 1


def test_submit_changed_spec_persists_child(session, seeded_pipeline) -> None:
    pipeline_id = _pipeline_id(seeded_pipeline)
    submit = SubmitSpec(SqlAlchemySpecVersionRepository(session))

    first = submit.submit(pipeline_id, _spec(destination="analytics.orders"))
    second = submit.submit(pipeline_id, _spec(destination="analytics.orders_v2"))

    records = (
        session.execute(
            select(SpecVersionRecord)
            .where(SpecVersionRecord.pipeline_id == pipeline_id)
            .order_by(SpecVersionRecord.seq)
        )
        .scalars()
        .all()
    )

    assert first.created is True
    assert second.created is True
    assert len(records) == 2
    assert records[1].parent_id == records[0].version_id
    assert second.version.parent_id == first.version.version_id


def test_same_parent_fork_is_rejected(session, seeded_pipeline) -> None:
    pipeline_id = _pipeline_id(seeded_pipeline)
    repo = SqlAlchemySpecVersionRepository(session)

    root = SpecVersion(
        version_id=uuid4(),
        pipeline_id=pipeline_id,
        spec_id="a" * 64,
        parent_id=None,
        content='{"version":"a"}',
        created_at=datetime.now(UTC),
    )
    first_child = SpecVersion(
        version_id=uuid4(),
        pipeline_id=pipeline_id,
        spec_id="b" * 64,
        parent_id=root.version_id,
        content='{"version":"b"}',
        created_at=datetime.now(UTC),
    )
    forked_child = SpecVersion(
        version_id=uuid4(),
        pipeline_id=pipeline_id,
        spec_id="c" * 64,
        parent_id=root.version_id,
        content='{"version":"c"}',
        created_at=datetime.now(UTC),
    )

    repo.add(root)
    repo.add(first_child)

    with pytest.raises(IntegrityError):
        with session.begin_nested():
            repo.add(forked_child)


def test_breaking_override_persists_across_round_trip(
    session,
    seeded_pipeline,
) -> None:
    pipeline_id = _pipeline_id(seeded_pipeline)
    repo = SqlAlchemySpecVersionRepository(session)
    submit = SubmitSpec(repo)

    submit.submit(pipeline_id, _spec())

    result = submit.submit(
        pipeline_id,
        _dropped_amount_spec(),
        allow_breaking=True,
    )

    assert result.version.breaking_override is True

    session.expire_all()

    head = repo.head_for(pipeline_id)

    assert head is not None
    assert head.breaking_override is True


def test_heads_returns_latest_version_for_each_pipeline(session) -> None:
    team = TeamRecord(id=uuid4(), name="analytics_heads", created_at=datetime.now(UTC))
    session.add(team)
    session.flush()
    first_pipeline = PipelineRecord(
        id=uuid4(),
        team_id=team.id,
        name="orders",
        created_at=team.created_at,
    )
    second_pipeline = PipelineRecord(
        id=uuid4(),
        team_id=team.id,
        name="customers",
        created_at=team.created_at,
    )
    session.add_all([first_pipeline, second_pipeline])
    session.flush()

    repo = SqlAlchemySpecVersionRepository(session)
    submit = SubmitSpec(repo)
    first_initial = submit.submit(first_pipeline.id, _spec(destination="analytics.orders"))
    first_head = submit.submit(first_pipeline.id, _spec(destination="analytics.orders_v2"))
    second_head = submit.submit(second_pipeline.id, _spec(destination="analytics.customers"))

    heads = repo.heads()

    assert first_initial.version not in heads
    assert set(heads) == {first_head.version, second_head.version}


def test_platform_lineage_graph_builds_from_persisted_heads(session) -> None:
    team = TeamRecord(id=uuid4(), name="analytics_lineage", created_at=datetime.now(UTC))
    session.add(team)
    session.flush()
    orders_pipeline = PipelineRecord(
        id=uuid4(),
        team_id=team.id,
        name="orders",
        created_at=team.created_at,
    )
    customers_pipeline = PipelineRecord(
        id=uuid4(),
        team_id=team.id,
        name="customers",
        created_at=team.created_at,
    )
    session.add_all([orders_pipeline, customers_pipeline])
    session.flush()

    repo = SqlAlchemySpecVersionRepository(session)
    submit = SubmitSpec(repo)
    submit.submit(
        orders_pipeline.id,
        _spec(
            destination="raw.orders",
            source_path="tests/fixtures/orders.csv",
            transform="mart_orders",
        ),
    )
    submit.submit(
        customers_pipeline.id,
        _spec(
            destination="raw.customers",
            source_path="tests/fixtures/customers.csv",
            transform="mart_customers",
        ),
    )

    graph = build_lineage_graph(repo.heads())

    assert graph.impacted_by("source:csv:tests/fixtures/orders.csv") == frozenset(
        {"raw.orders", "main.mart_orders"}
    )
    assert graph.impacted_by("source:csv:tests/fixtures/customers.csv") == frozenset(
        {"raw.customers", "main.mart_customers"}
    )
