from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select

from keel.adapters.db.models import SpecVersionRecord
from keel.adapters.db.spec_version_repository import SqlAlchemySpecVersionRepository
from keel.application.specs.parser import parse_pipeline_spec_yaml
from keel.application.use_cases.submit_spec import SubmitSpec
from keel.application.specs.versioning import SpecVersion


def _pipeline_id(seeded_pipeline) -> UUID:
    return seeded_pipeline if isinstance(seeded_pipeline, UUID) else seeded_pipeline.id


def _spec(destination: str = "analytics.orders"):
    return parse_pipeline_spec_yaml(f"""name: orders_daily
team: analytics
owner: data-platform@example.com
source:
  type: csv
  path: tests/fixtures/orders.csv
contract:
  - name: order_id
    type: string
  - name: amount
    type: decimal
destination: {destination}
freshness:
  max_age_minutes: 60
quality_checks: []
""")


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
