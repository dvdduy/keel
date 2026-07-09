from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from keel.application.agent.dossier import DatasetOwner, RunView, assemble_dossier
from keel.application.incident.model import Incident, IncidentStatus
from keel.application.slo.model import SloEvaluation, SloStatus


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SPEC_VERSION_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
INCIDENT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


class FakePlatformReader:
    def __init__(self) -> None:
        self.impacts: dict[str, frozenset[str]] = {"raw.orders": frozenset({"mart.orders"})}
        self.owners: dict[str, DatasetOwner] = {
            "mart.orders": DatasetOwner(
                dataset="mart.orders",
                team="analytics",
                owner="analytics-oncall@example.com",
            )
        }
        self.runs: dict[UUID, RunView] = {
            RUN_ID: RunView(run_id=RUN_ID, status="failed", failed_steps=("quality:unique",))
        }
        self.spec_heads: dict[UUID, UUID] = {PIPELINE_ID: SPEC_VERSION_ID}
        self.calls: list[tuple[str, object]] = []

    async def lineage_impact(self, dataset: str) -> frozenset[str]:
        self.calls.append(("lineage_impact", dataset))
        return self.impacts[dataset]

    async def catalog_show(self, dataset: str) -> DatasetOwner | None:
        self.calls.append(("catalog_show", dataset))
        return self.owners.get(dataset)

    async def run_show(self, run_id: UUID) -> RunView | None:
        self.calls.append(("run_show", run_id))
        return self.runs.get(run_id)

    async def spec_head(self, pipeline_id: UUID) -> UUID | None:
        self.calls.append(("spec_head", pipeline_id))
        return self.spec_heads.get(pipeline_id)


def _run(coro):
    return asyncio.run(coro)


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


def _incident(
    *,
    run_id: UUID | None = RUN_ID,
    impacted: frozenset[str] = frozenset({"mart.orders"}),
) -> Incident:
    return Incident(
        id=INCIDENT_ID,
        subject="raw.orders",
        pipeline_id=PIPELINE_ID,
        slo_name="freshness",
        status=IncidentStatus.OPEN,
        evaluation=_evaluation(),
        run_id=run_id,
        team="revenue",
        owner="data-oncall@example.com",
        impacted=impacted,
        opened_at=NOW,
    )


def test_dossier_reports_live_blast_radius() -> None:
    reader = FakePlatformReader()

    dossier = _run(assemble_dossier(_incident(), reader))

    assert dossier.subject == "raw.orders"
    assert dossier.live_impacted == frozenset({"mart.orders"})


def test_dossier_resolves_owner_for_each_impacted_dataset() -> None:
    reader = FakePlatformReader()
    reader.impacts["raw.orders"] = frozenset({"mart.orders", "mart.revenue"})
    reader.owners["mart.revenue"] = DatasetOwner(
        dataset="mart.revenue",
        team="finance",
        owner="finance-oncall@example.com",
    )

    dossier = _run(assemble_dossier(_incident(impacted=reader.impacts["raw.orders"]), reader))

    assert dossier.impacted_owners == (
        DatasetOwner("mart.orders", "analytics", "analytics-oncall@example.com"),
        DatasetOwner("mart.revenue", "finance", "finance-oncall@example.com"),
    )


def test_dossier_includes_failing_run_when_run_id_present() -> None:
    reader = FakePlatformReader()

    dossier = _run(assemble_dossier(_incident(), reader))

    assert dossier.failing_run == RunView(
        run_id=RUN_ID,
        status="failed",
        failed_steps=("quality:unique",),
    )


def test_dossier_omits_run_and_skips_run_show_when_no_run_id() -> None:
    reader = FakePlatformReader()

    dossier = _run(assemble_dossier(_incident(run_id=None), reader))

    assert dossier.failing_run is None
    assert ("run_show", RUN_ID) not in reader.calls


def test_dossier_captures_current_spec_version() -> None:
    reader = FakePlatformReader()

    dossier = _run(assemble_dossier(_incident(), reader))

    assert dossier.spec_version_id == SPEC_VERSION_ID


def test_dossier_records_gap_when_impacted_dataset_missing_from_catalog() -> None:
    reader = FakePlatformReader()
    reader.impacts["raw.orders"] = frozenset({"mart.orders", "mart.unknown"})

    dossier = _run(assemble_dossier(_incident(impacted=reader.impacts["raw.orders"]), reader))

    assert "catalog owner missing for impacted dataset mart.unknown" in dossier.gaps
    assert dossier.impacted_owners == (
        DatasetOwner("mart.orders", "analytics", "analytics-oncall@example.com"),
    )


def test_dossier_flags_impact_drift_when_live_differs_from_incident_snapshot() -> None:
    reader = FakePlatformReader()
    reader.impacts["raw.orders"] = frozenset({"mart.orders", "mart.revenue"})

    dossier = _run(assemble_dossier(_incident(impacted=frozenset({"mart.orders"})), reader))

    assert dossier.impact_drifted is True


def test_assemble_dossier_issues_only_reads() -> None:
    reader = FakePlatformReader()

    _run(assemble_dossier(_incident(), reader))

    assert {method for method, _ in reader.calls} <= {
        "lineage_impact",
        "catalog_show",
        "run_show",
        "spec_head",
    }
    assert reader.calls == [
        ("lineage_impact", "raw.orders"),
        ("catalog_show", "mart.orders"),
        ("run_show", RUN_ID),
        ("spec_head", PIPELINE_ID),
    ]
