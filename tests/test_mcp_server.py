from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
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
from keel.entrypoints.mcp_server import (
    ReadOnlyControlPlane,
    build_mcp_server,
    catalog_list,
    catalog_show,
    lineage_impact,
    run_show,
    spec_head,
)


T = TypeVar("T")


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


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)


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


def _client_factory(app: FastAPI) -> Callable[[str], httpx.AsyncClient]:
    def create(base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)

    return create


def _orders_spec_yaml() -> str:
    return """name: orders_daily
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
destination: analytics.orders
freshness:
  max_age_minutes: 60
quality_checks: []
"""


async def _seeded_control_plane() -> tuple[ReadOnlyControlPlane, UUID, UUID]:
    runs = FakeRunRepository()
    run = Run(
        id=uuid4(),
        pipeline_id=uuid4(),
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
        status=RunStatus.SUCCESS,
        watermark="2026-07-09",
    )
    runs.add(run)
    app = _app(runs=runs)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    pipeline_id = uuid4()
    response = await client.post(
        f"/pipelines/{pipeline_id}/specs",
        params={"allow_breaking": False},
        content=_orders_spec_yaml(),
        headers={"content-type": "application/x-yaml"},
    )
    assert response.status_code == 201
    return ReadOnlyControlPlane(client), pipeline_id, run.id


def test_catalog_list_returns_expected_data() -> None:
    async def run() -> None:
        cp, _, _ = await _seeded_control_plane()
        try:
            result = await catalog_list(cp)
        finally:
            await cp._client.aclose()

        assert isinstance(result, list)
        assert result[0]["dataset"] == "analytics.orders"
        assert result[0]["columns"][0] == {
            "name": "order_id",
            "type": "integer",
            "nullable": False,
        }

    _run(run())


def test_catalog_show_returns_expected_data() -> None:
    async def run() -> None:
        cp, _, _ = await _seeded_control_plane()
        try:
            result = await catalog_show(cp, "analytics.orders")
        finally:
            await cp._client.aclose()

        assert isinstance(result, dict)
        assert result["dataset"] == "analytics.orders"
        assert result["owner"] == "data-platform@example.com"

    _run(run())


def test_run_show_returns_expected_data() -> None:
    async def run() -> None:
        cp, _, run_id = await _seeded_control_plane()
        try:
            result = await run_show(cp, run_id)
        finally:
            await cp._client.aclose()

        assert isinstance(result, dict)
        assert result["id"] == str(run_id)
        assert result["status"] == "success"

    _run(run())


def test_lineage_impact_returns_expected_data() -> None:
    async def run() -> None:
        cp, _, _ = await _seeded_control_plane()
        try:
            result = await lineage_impact(cp, "analytics.orders")
        finally:
            await cp._client.aclose()

        assert result == {"dataset": "analytics.orders", "impacted": []}

    _run(run())


def test_spec_head_returns_expected_data() -> None:
    async def run() -> None:
        cp, pipeline_id, _ = await _seeded_control_plane()
        try:
            result = await spec_head(cp, pipeline_id)
        finally:
            await cp._client.aclose()

        assert isinstance(result, dict)
        assert result["pipeline_id"] == str(pipeline_id)
        assert result["parent_id"] is None
        assert result["breaking_override"] is False

    _run(run())


def test_missing_resources_return_structured_not_found() -> None:
    async def run() -> None:
        cp, _, _ = await _seeded_control_plane()
        try:
            assert await catalog_show(cp, "analytics.unknown") == {
                "status": 404,
                "error": "catalog entry not found",
            }
            assert await run_show(cp, uuid4()) == {"status": 404, "error": "run not found"}
            assert await spec_head(cp, uuid4()) == {
                "status": 404,
                "error": "pipeline spec head not found",
            }
            assert await lineage_impact(cp, "analytics.unknown") == {
                "status": 404,
                "error": "lineage dataset not found",
            }
        finally:
            await cp._client.aclose()

    _run(run())


def test_read_only_control_plane_exposes_no_write_verbs() -> None:
    cp = ReadOnlyControlPlane(httpx.AsyncClient(base_url="http://testserver"))

    assert not hasattr(cp, "post")
    assert not hasattr(cp, "put")
    assert not hasattr(cp, "delete")
    assert not hasattr(cp, "patch")

    _run(cp._client.aclose())


def test_mcp_server_registers_only_read_tools() -> None:
    async def run() -> None:
        app = _app()
        server = build_mcp_server(client_factory=_client_factory(app))

        tools = await server.list_tools()
        tool_names = {tool.name for tool in tools}

        assert tool_names == {
            "catalog_list",
            "catalog_show",
            "run_show",
            "lineage_impact",
            "spec_head",
        }
        assert not tool_names & {"post", "put", "delete", "patch"}

    _run(run())


def test_tool_functions_issue_only_get_requests() -> None:
    seen_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        return httpx.Response(200, json={})

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://testserver",
        ) as client:
            cp = ReadOnlyControlPlane(client)
            await catalog_list(cp)
            await catalog_show(cp, "analytics.orders")
            await run_show(cp, uuid4())
            await lineage_impact(cp, "analytics.orders")
            await spec_head(cp, uuid4())

    _run(run())

    assert seen_methods == ["GET", "GET", "GET", "GET", "GET"]
