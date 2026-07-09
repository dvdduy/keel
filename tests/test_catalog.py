from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from keel.application.catalog.entry import CatalogEntry, project_catalog_entry
from keel.application.specs.models import (
    ColumnType,
    ContractColumn,
    FreshnessSpec,
    PipelineSpec,
    SourceSpec,
    SourceType,
)
from keel.application.specs.versioning import (
    SpecVersion,
    canonical_spec_json,
    spec_content_hash,
)


class FakeDatasetCatalog:
    def __init__(self) -> None:
        self._by_dataset: dict[str, CatalogEntry] = {}

    def upsert(self, entry: CatalogEntry) -> None:
        self._by_dataset[entry.dataset] = entry

    def get(self, dataset: str) -> CatalogEntry | None:
        return self._by_dataset.get(dataset)

    def list(self) -> tuple[CatalogEntry, ...]:
        return tuple(self._by_dataset.values())


def _version() -> SpecVersion:
    spec = PipelineSpec(
        name="orders_daily",
        team="analytics",
        owner="alice@example.com",
        source=SourceSpec(type=SourceType.CSV, path="orders.csv"),
        destination="analytics.orders",
        contract=(
            ContractColumn(name="order_id", type=ColumnType.INTEGER, nullable=False),
            ContractColumn(name="amount", type=ColumnType.DECIMAL),
        ),
        freshness=FreshnessSpec(max_age_minutes=60),
    )
    return SpecVersion(
        version_id=uuid4(),
        pipeline_id=uuid4(),
        spec_id=spec_content_hash(spec),
        parent_id=None,
        content=canonical_spec_json(spec),
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
    )


def test_project_catalog_entry_maps_owner_team_and_schema() -> None:
    entry = project_catalog_entry(_version())

    assert entry.owner == "alice@example.com"
    assert entry.team == "analytics"
    assert [column.name for column in entry.columns] == ["order_id", "amount"]


def test_project_catalog_entry_uses_destination_as_dataset_identity() -> None:
    assert project_catalog_entry(_version()).dataset == "analytics.orders"


def test_project_catalog_entry_records_source_spec_id_provenance() -> None:
    version = _version()

    assert project_catalog_entry(version).source_spec_id == version.spec_id


def test_upsert_new_dataset_is_listed() -> None:
    catalog = FakeDatasetCatalog()
    entry = project_catalog_entry(_version())

    catalog.upsert(entry)

    assert catalog.list() == (entry,)


def test_upsert_same_dataset_updates_owner_without_duplicating() -> None:
    catalog = FakeDatasetCatalog()
    entry = project_catalog_entry(_version())

    catalog.upsert(entry)
    catalog.upsert(replace(entry, owner="bob@example.com"))

    assert len(catalog.list()) == 1
    assert catalog.get(entry.dataset).owner == "bob@example.com"  # type: ignore[union-attr]


def test_get_unknown_dataset_returns_none() -> None:
    assert FakeDatasetCatalog().get("analytics.unknown") is None
