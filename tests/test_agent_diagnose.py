from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import UUID

from keel.application.agent.diagnose import HypothesisStatus, diagnose
from keel.application.agent.dossier import DatasetOwner, RunView, assemble_dossier
from keel.application.incident.model import Incident, IncidentStatus
from keel.application.slo.model import SloEvaluation, SloStatus


T = TypeVar("T")
NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SPEC_VERSION_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
INCIDENT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
SPEC_DIFF_GAP = "correlated changes unavailable: no spec history/diff read endpoint"


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

    async def lineage_impact(self, dataset: str) -> frozenset[str]:
        return self.impacts[dataset]

    async def catalog_show(self, dataset: str) -> DatasetOwner | None:
        return self.owners.get(dataset)

    async def run_show(self, run_id: UUID) -> RunView | None:
        return self.runs.get(run_id)

    async def spec_head(self, pipeline_id: UUID) -> UUID | None:
        return self.spec_heads.get(pipeline_id)


def _run(coro) -> T:
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


def _incident(*, impacted: frozenset[str] = frozenset({"mart.orders"})) -> Incident:
    return Incident(
        id=INCIDENT_ID,
        subject="raw.orders",
        pipeline_id=PIPELINE_ID,
        slo_name="freshness",
        status=IncidentStatus.OPEN,
        evaluation=_evaluation(),
        run_id=RUN_ID,
        team="revenue",
        owner="data-oncall@example.com",
        impacted=impacted,
        opened_at=NOW,
    )


def _diagnose(reader: FakePlatformReader, incident: Incident | None = None):
    dossier = _run(assemble_dossier(incident or _incident(), reader))
    return diagnose(dossier)


def _hypothesis_statuses(reader: FakePlatformReader) -> dict[str, HypothesisStatus]:
    diagnosis = _diagnose(reader)
    return {hypothesis.kind: hypothesis.status for hypothesis in diagnosis.hypotheses}


def test_diagnose_confirms_quality_gate_failure_from_failing_run() -> None:
    statuses = _hypothesis_statuses(FakePlatformReader())

    assert statuses["quality_gate_failure"] == HypothesisStatus.CONFIRMED


def test_diagnose_refutes_quality_gate_when_failure_not_at_quality_step() -> None:
    reader = FakePlatformReader()
    reader.runs[RUN_ID] = RunView(run_id=RUN_ID, status="failed", failed_steps=("transform",))

    diagnosis = _diagnose(reader)

    quality = next(
        hypothesis
        for hypothesis in diagnosis.hypotheses
        if hypothesis.kind == "quality_gate_failure"
    )
    assert quality.status == HypothesisStatus.REFUTED
    assert "failed steps are not quality gates: transform" in quality.evidence


def test_diagnose_leaves_upstream_change_unverified_citing_the_gap() -> None:
    diagnosis = _diagnose(FakePlatformReader())

    upstream = next(
        hypothesis
        for hypothesis in diagnosis.hypotheses
        if hypothesis.kind == "upstream_spec_change"
    )
    assert upstream.status == HypothesisStatus.UNVERIFIED
    assert upstream.evidence == (SPEC_DIFF_GAP,)


def test_diagnose_confirms_lineage_drift_when_impact_drifted() -> None:
    reader = FakePlatformReader()
    reader.impacts["raw.orders"] = frozenset({"mart.orders", "mart.revenue"})
    reader.owners["mart.revenue"] = DatasetOwner(
        dataset="mart.revenue",
        team="finance",
        owner="finance-oncall@example.com",
    )

    diagnosis = _diagnose(reader, _incident(impacted=frozenset({"mart.orders"})))

    lineage = next(
        hypothesis for hypothesis in diagnosis.hypotheses if hypothesis.kind == "lineage_drift"
    )
    assert lineage.status == HypothesisStatus.CONFIRMED


def test_diagnose_ranks_confirmed_above_unverified() -> None:
    diagnosis = _diagnose(FakePlatformReader())

    statuses = tuple(hypothesis.status for hypothesis in diagnosis.hypotheses)
    ranks = tuple(hypothesis.rank for hypothesis in diagnosis.hypotheses)

    assert statuses == (HypothesisStatus.CONFIRMED, HypothesisStatus.UNVERIFIED)
    assert ranks == (1, 2)


def test_diagnose_runbook_cites_evidence_for_each_confirmed_hypothesis() -> None:
    diagnosis = _diagnose(FakePlatformReader())

    for hypothesis in diagnosis.hypotheses:
        if hypothesis.status == HypothesisStatus.CONFIRMED:
            runbook_line = diagnosis.runbook[hypothesis.rank - 1]
            for evidence in hypothesis.evidence:
                assert evidence in runbook_line


def test_diagnose_over_assembled_dossier_end_to_end() -> None:
    diagnosis = _diagnose(FakePlatformReader())

    assert diagnosis.subject == "raw.orders"
    assert tuple(hypothesis.kind for hypothesis in diagnosis.hypotheses) == (
        "quality_gate_failure",
        "upstream_spec_change",
    )
    assert diagnosis.runbook == (
        (
            f"Investigate the failed quality gate; evidence: run {RUN_ID} status failed; "
            "failed quality step quality:unique."
        ),
        (
            "Could not verify an upstream spec change: "
            f"{SPEC_DIFF_GAP} - compare recent spec versions manually."
        ),
    )
