from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
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
from keel.domain.run import Run, RunKey
from keel.entrypoints import cli
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


def _orders_spec_yaml(extra_contract: str = "") -> str:
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
{extra_contract}destination: analytics.orders
freshness:
  max_age_minutes: 60
quality_checks: []
"""


def _write_spec(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_submit_new_spec_exits_zero(tmp_path: Path, capsys) -> None:
    app = _app()
    pipeline_id = uuid4()
    spec_path = _write_spec(tmp_path / "orders.yaml", _orders_spec_yaml())

    code = cli.main(
        ["spec", "submit", str(pipeline_id), str(spec_path)],
        client_factory=_client_factory(app),
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "accepted" in output
    assert str(pipeline_id) in output


def test_submit_breaking_spec_prints_diff_exits_nonzero(tmp_path: Path, capsys) -> None:
    app = _app()
    pipeline_id = uuid4()
    original = _write_spec(tmp_path / "orders.yaml", _orders_spec_yaml())
    breaking = _write_spec(
        tmp_path / "orders_breaking.yaml",
        _orders_spec_yaml(
            """  - name: required_note
    type: string
    nullable: false
"""
        ),
    )
    assert (
        cli.main(
            ["spec", "submit", str(pipeline_id), str(original)],
            client_factory=_client_factory(app),
        )
        == 0
    )
    capsys.readouterr()

    code = cli.main(
        ["spec", "submit", str(pipeline_id), str(breaking)],
        client_factory=_client_factory(app),
    )

    assert code == 1
    output = capsys.readouterr().out
    assert "Breaking spec change rejected" in output
    assert "required_note" in output
    assert "new required column was added" in output


def test_invalid_spec_prints_diagnostics(tmp_path: Path, capsys) -> None:
    app = _app()
    spec_path = _write_spec(tmp_path / "invalid.yaml", "name: [")

    code = cli.main(
        ["spec", "submit", str(uuid4()), str(spec_path)],
        client_factory=_client_factory(app),
    )

    assert code == 1
    output = capsys.readouterr().out
    assert "(root): pipeline spec YAML is malformed" in output


def test_run_show_not_found_exits_nonzero(capsys) -> None:
    app = _app()
    run_id = uuid4()

    code = cli.main(["run", "show", str(run_id)], client_factory=_client_factory(app))

    assert code == 1
    output = capsys.readouterr().out
    assert "Not found" in output
    assert "run not found" in output


def test_json_flag_emits_parseable_json(tmp_path: Path, capsys) -> None:
    app = _app()
    pipeline_id = uuid4()
    spec_path = _write_spec(tmp_path / "orders.yaml", _orders_spec_yaml())

    code = cli.main(
        ["spec", "submit", str(pipeline_id), str(spec_path), "--json"],
        client_factory=_client_factory(app),
    )

    assert code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["pipeline_id"] == str(pipeline_id)
    assert body["parent_id"] is None


def test_unreachable_control_plane_reports_cleanly(capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def factory(base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)

    code = cli.main(
        ["catalog", "list"],
        client_factory=factory,
        environ={"KEEL_API_URL": "http://127.0.0.1:9999"},
    )

    assert code == 1
    output = capsys.readouterr().out
    assert "control plane is not reachable" in output
    assert "http://127.0.0.1:9999" in output
    assert "Traceback" not in output
