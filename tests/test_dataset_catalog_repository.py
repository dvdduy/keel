from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from keel.adapters.db.dataset_catalog import SqlAlchemyDatasetCatalog
from keel.adapters.db.models import DatasetRecord
from keel.adapters.db.spec_version_repository import SqlAlchemySpecVersionRepository
from keel.application.specs.parser import parse_pipeline_spec_yaml
from keel.application.use_cases.submit_spec import SubmitSpec


def _spec(owner: str):
    return parse_pipeline_spec_yaml(
        f"""name: orders_daily
team: analytics
owner: {owner}
source:
  type: csv
  path: tests/fixtures/orders.csv
contract:
  - name: order_id
    type: string
  - name: amount
    type: decimal
destination: analytics.orders
freshness:
  max_age_minutes: 60
"""
    )


def test_submit_projects_dataset_and_updates_same_row(session, seeded_pipeline) -> None:
    pipeline_id = seeded_pipeline if isinstance(seeded_pipeline, UUID) else seeded_pipeline.id
    catalog = SqlAlchemyDatasetCatalog(session)
    submit = SubmitSpec(SqlAlchemySpecVersionRepository(session), catalog)

    first = submit.submit(pipeline_id, _spec("alice@example.com"))
    second = submit.submit(pipeline_id, _spec("bob@example.com"))

    entry = catalog.get("analytics.orders")
    count = session.scalar(select(func.count()).select_from(DatasetRecord))
    assert entry is not None
    assert count == 1
    assert entry.owner == "bob@example.com"
    assert entry.team == "analytics"
    assert [column.name for column in entry.columns] == ["order_id", "amount"]
    assert entry.source_spec_id == second.version.spec_id
    assert entry.source_spec_id != first.version.spec_id
