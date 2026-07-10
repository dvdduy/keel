from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from keel.adapters.agent.graph import build_incident_agent
from keel.adapters.agent.http_reader import HttpPlatformReader
from keel.adapters.control_plane.read_only_client import ReadOnlyControlPlane
from keel.application.agent.diagnose import HypothesisStatus
from keel.application.agent.dossier import DatasetOwner, RunView
from keel.application.catalog.entry import CatalogEntry
from keel.application.incident.model import Incident, IncidentStatus
from keel.application.ports.catalog import DatasetCatalog
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.spec_version_repo import SpecVersionRepository
from keel.application.specs.versioning import SpecVersion
from keel.application.slo.model import SloEvaluation, SloStatus
from keel.application.use_cases.submit_spec import SubmitSpec
from keel.domain.run import Run, RunKey, RunStatus, RunStep
from keel.entrypoints.api import create_app
from keel.entrypoints.dependencies import get_catalog, get_runs, get_spec_versions, get_submit_spec


T = TypeVar("T")
NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


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


class FakePlatformReader:
    async def lineage_impact(self, dataset: str) -> frozenset[str]:
        return frozenset({"mart.orders"})

    async def catalog_show(self, dataset: str) -> DatasetOwner | None:
        return DatasetOwner(dataset, "analytics", "analytics-oncall@example.com")

    async def run_show(self, run_id: UUID) -> RunView | None:
        return RunView(run_id, "failed", ("quality:unique",))

    async def spec_head(self, pipeline_id: UUID) -> UUID | None:
        return UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)


def _orders_spec_yaml(destination: str = "analytics.orders") -> str:
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
    nullable: true
destination: {destination}
freshness:
  max_age_minutes: 60
quality_checks: []
"""


def _app(
    *,
    versions: FakeSpecVersionRepository | None = None,
    catalog: FakeDatasetCatalog | None = None,
    runs: FakeRunRepository | None = None,
) -> FastAPI:
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
    return app


async def _seeded_reader() -> tuple[HttpPlatformReader, httpx.AsyncClient, UUID]:
    runs = FakeRunRepository()
    run = Run(
        id=RUN_ID,
        pipeline_id=PIPELINE_ID,
        created_at=NOW - timedelta(minutes=5),
        status=RunStatus.FAILED,
        started_at=NOW - timedelta(minutes=5),
        finished_at=NOW - timedelta(minutes=1),
    )
    run.add_step(
        RunStep(
            id=uuid4(),
            run_id=RUN_ID,
            name="quality:unique",
            sequence=1,
            created_at=NOW - timedelta(minutes=2),
            status=RunStatus.FAILED,
        )
    )
    runs.add(run)

    app = _app(runs=runs)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    response = await client.post(
        f"/pipelines/{PIPELINE_ID}/specs",
        params={"allow_breaking": False},
        content=_orders_spec_yaml(),
        headers={"content-type": "application/x-yaml"},
    )
    assert response.status_code == 201
    return HttpPlatformReader(ReadOnlyControlPlane(client)), client, response.json()["version_id"]


def _evaluation() -> SloEvaluation:
    return SloEvaluation(
        objective=0.9,
        window_start=NOW - timedelta(days=30),
        window_end=NOW,
        total=10,
        good=4,
        bad=6,
        unknown=0,
        attainment=0.4,
        status=SloStatus.BREACHING,
        error_budget_total=1.0,
        error_budget_consumed=6.0,
        error_budget_remaining=-5.0,
    )


def _incident() -> Incident:
    return Incident(
        id=uuid4(),
        subject="analytics.orders",
        pipeline_id=PIPELINE_ID,
        slo_name="freshness",
        status=IncidentStatus.OPEN,
        evaluation=_evaluation(),
        run_id=RUN_ID,
        team="analytics",
        owner="data-platform@example.com",
        impacted=frozenset(),
        opened_at=NOW,
    )


def test_http_platform_reader_maps_control_plane_json_to_read_models() -> None:
    async def run() -> None:
        reader, client, version_id = await _seeded_reader()
        try:
            assert await reader.lineage_impact("analytics.orders") == frozenset()
            assert await reader.catalog_show("analytics.orders") == DatasetOwner(
                "analytics.orders",
                "analytics",
                "data-platform@example.com",
            )
            assert await reader.run_show(RUN_ID) == RunView(
                RUN_ID,
                "failed",
                ("quality:unique",),
            )
            assert await reader.spec_head(PIPELINE_ID) == UUID(version_id)
        finally:
            await client.aclose()

    _run(run())


def test_http_platform_reader_returns_none_for_not_found_optional_reads() -> None:
    async def run() -> None:
        reader, client, _ = await _seeded_reader()
        try:
            assert await reader.catalog_show("analytics.unknown") is None
            assert await reader.run_show(uuid4()) is None
            assert await reader.spec_head(uuid4()) is None
        finally:
            await client.aclose()

    _run(run())


def test_langgraph_agent_produces_ranked_diagnosis() -> None:
    async def run() -> None:
        graph = build_incident_agent(FakePlatformReader())

        result = await graph.ainvoke({"incident": _incident()})

        assert result["dossier"].subject == "analytics.orders"
        assert result["dossier"].failing_run == RunView(
            RUN_ID,
            "failed",
            ("quality:unique",),
        )
        assert result["diagnosis"].subject == "analytics.orders"
        assert tuple(hypothesis.kind for hypothesis in result["diagnosis"].hypotheses) == (
            "quality_gate_failure",
            "lineage_drift",
            "upstream_spec_change",
        )
        assert tuple(hypothesis.status for hypothesis in result["diagnosis"].hypotheses) == (
            HypothesisStatus.CONFIRMED,
            HypothesisStatus.CONFIRMED,
            HypothesisStatus.UNVERIFIED,
        )
        assert tuple(hypothesis.rank for hypothesis in result["diagnosis"].hypotheses) == (1, 2, 3)

    _run(run())
