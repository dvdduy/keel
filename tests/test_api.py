from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from keel.application.catalog.entry import CatalogEntry
from keel.application.ports.catalog import DatasetCatalog
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.spec_version_repo import SpecVersionRepository
from keel.application.specs.versioning import SpecVersion
from keel.application.use_cases.submit_spec import SubmitSpec
from keel.domain.run import Run, RunKey, RunStatus
from keel.entrypoints.api import create_app
from keel.entrypoints.dependencies import get_catalog, get_runs, get_spec_versions, get_submit_spec


class FakeSpecVersionRepository:
    def __init__(self) -> None:
        self.history: dict[UUID, list[SpecVersion]] = defaultdict(list)

    def head_for(self, pipeline_id: UUID) -> SpecVersion | None:
        versions = self.history[pipeline_id]
        return versions[-1] if versions else None

    def heads(self) -> tuple[SpecVersion, ...]:
        return tuple(versions[-1] for versions in self.history.values() if versions)

    def add(self, version: SpecVersion) -> None:
        self.history[version.pipeline_id].append(version)


class FakeDatasetCatalog:
    def __init__(self) -> None:
        self._by_dataset: dict[str, CatalogEntry] = {}

    def upsert(self, entry: CatalogEntry) -> None:
        self._by_dataset[entry.dataset] = entry

    def get(self, dataset: str) -> CatalogEntry | None:
        return self._by_dataset.get(dataset)

    def list(self) -> tuple[CatalogEntry, ...]:
        return tuple(self._by_dataset.values())


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, Run] = {}

    def add(self, run: Run) -> None:
        self.runs[run.id] = run

    def get(self, run_id: UUID) -> Run | None:
        return self.runs.get(run_id)

    def latest_for_key(self, key: RunKey) -> Run | None:
        matches = [
            run
            for run in self.runs.values()
            if run.pipeline_id == key.pipeline_id and run.watermark == key.watermark
        ]
        return matches[-1] if matches else None


def _client(
    *,
    versions: FakeSpecVersionRepository | None = None,
    catalog: FakeDatasetCatalog | None = None,
    runs: FakeRunRepository | None = None,
) -> TestClient:
    versions = versions or FakeSpecVersionRepository()
    catalog = catalog or FakeDatasetCatalog()
    runs = runs or FakeRunRepository()
    app = create_app(sessionmaker[Session]())

    def override_versions() -> SpecVersionRepository:
        return versions

    def override_catalog() -> DatasetCatalog:
        return catalog

    def override_runs() -> RunRepository:
        return runs

    def override_submit_spec() -> SubmitSpec:
        return SubmitSpec(versions=versions, catalog=catalog)

    app.dependency_overrides[get_spec_versions] = override_versions
    app.dependency_overrides[get_catalog] = override_catalog
    app.dependency_overrides[get_runs] = override_runs
    app.dependency_overrides[get_submit_spec] = override_submit_spec
    return TestClient(app)


def _orders_spec_yaml(
    *,
    destination: str = "analytics.orders",
    extra_contract: str = "",
) -> str:
    return f"""name: orders_daily
team: analytics
owner: data-platform@example.com
source:
  type: csv
  path: tests/fixtures/orders.csv
contract:
  - name: order_id
    type: integer
    nullable: false
  - name: amount
    type: decimal
{extra_contract}destination: {destination}
freshness:
  max_age_minutes: 60
quality_checks: []
"""


def _post_spec(
    client: TestClient,
    pipeline_id: UUID,
    yaml_text: str,
    *,
    allow_breaking: bool = False,
):
    return client.post(
        f"/pipelines/{pipeline_id}/specs",
        params={"allow_breaking": allow_breaking},
        content=yaml_text,
        headers={"content-type": "application/x-yaml"},
    )


def test_submit_new_spec_returns_201_with_version() -> None:
    pipeline_id = uuid4()
    response = _post_spec(_client(), pipeline_id, _orders_spec_yaml())

    assert response.status_code == 201
    body = response.json()
    assert body["pipeline_id"] == str(pipeline_id)
    assert body["parent_id"] is None
    assert "content" not in body


def test_resubmit_identical_spec_returns_200_noop() -> None:
    pipeline_id = uuid4()
    client = _client()

    first = _post_spec(client, pipeline_id, _orders_spec_yaml())
    second = _post_spec(client, pipeline_id, _orders_spec_yaml())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["version_id"] == first.json()["version_id"]


def test_submit_breaking_change_returns_409_with_diff() -> None:
    pipeline_id = uuid4()
    client = _client()
    _post_spec(client, pipeline_id, _orders_spec_yaml())

    response = _post_spec(
        client,
        pipeline_id,
        _orders_spec_yaml(
            extra_contract="""  - name: required_note
    type: string
    nullable: false
"""
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["breaking_changes"] == [
        {
            "kind": "required_column_added",
            "column": "required_note",
            "detail": "new required column was added",
        }
    ]


def test_submit_breaking_change_with_allow_breaking_returns_201() -> None:
    pipeline_id = uuid4()
    client = _client()
    _post_spec(client, pipeline_id, _orders_spec_yaml())

    response = _post_spec(
        client,
        pipeline_id,
        _orders_spec_yaml(
            extra_contract="""  - name: required_note
    type: string
    nullable: false
"""
        ),
        allow_breaking=True,
    )

    assert response.status_code == 201
    assert response.json()["breaking_override"] is True


def test_malformed_spec_returns_422_with_keel_diagnostics() -> None:
    response = _post_spec(_client(), uuid4(), "name: [")

    assert response.status_code == 422
    assert response.json()["detail"]["diagnostics"] == [
        {"loc": "(root)", "message": "pipeline spec YAML is malformed"}
    ]


def test_get_head_returns_current_spec_version() -> None:
    pipeline_id = uuid4()
    client = _client()
    created = _post_spec(client, pipeline_id, _orders_spec_yaml()).json()

    response = client.get(f"/pipelines/{pipeline_id}/specs/head")

    assert response.status_code == 200
    assert response.json() == created


def test_get_head_unknown_pipeline_returns_404() -> None:
    response = _client().get(f"/pipelines/{uuid4()}/specs/head")

    assert response.status_code == 404


def test_get_catalog_lists_datasets() -> None:
    client = _client()
    _post_spec(client, uuid4(), _orders_spec_yaml())

    response = client.get("/catalog")

    assert response.status_code == 200
    assert response.json()[0]["dataset"] == "analytics.orders"
    assert response.json()[0]["columns"][0] == {
        "name": "order_id",
        "type": "integer",
        "nullable": False,
    }


def test_get_unknown_catalog_entry_returns_404() -> None:
    response = _client().get("/catalog/analytics.unknown")

    assert response.status_code == 404


def test_get_run_returns_persisted_run() -> None:
    runs = FakeRunRepository()
    run = Run(
        id=uuid4(),
        pipeline_id=uuid4(),
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
        status=RunStatus.SUCCESS,
        watermark="2026-07-09",
    )
    runs.add(run)

    response = _client(runs=runs).get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_get_lineage_impact_returns_downstream_closure() -> None:
    client = _client()
    _post_spec(
        client,
        uuid4(),
        _orders_spec_yaml(destination="analytics.orders", extra_contract=""),
    )

    response = client.get("/lineage/analytics.orders/impact")

    assert response.status_code == 200
    assert response.json() == {"dataset": "analytics.orders", "impacted": []}


def test_get_lineage_impact_unknown_dataset_returns_404() -> None:
    client = _client()
    _post_spec(client, uuid4(), _orders_spec_yaml(destination="analytics.orders"))

    response = client.get("/lineage/analytics.unknown/impact")

    assert response.status_code == 404
    assert response.json()["detail"] == "lineage dataset not found"


def test_openapi_schema_is_served() -> None:
    response = _client().get("/openapi.json")

    assert response.status_code == 200
