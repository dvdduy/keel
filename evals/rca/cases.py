from __future__ import annotations

from uuid import UUID

from keel.application.agent.dossier import DatasetOwner, IncidentDossier, RunView

from evals.rca.score import EvalCase


PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SPEC_VERSION_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SPEC_DIFF_GAP = "correlated changes unavailable: no spec history/diff read endpoint"


def cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            name="confirmed quality gate",
            dossier=_dossier(run=_run("00000000-0000-0000-0000-000000000001", "quality:unique")),
            expected_cause="quality_gate_failure",
            expect_confident=True,
        ),
        EvalCase(
            name="lineage drift alone",
            dossier=_dossier(run=None, impact_drifted=True),
            expected_cause="lineage_drift",
            expect_confident=True,
        ),
        EvalCase(
            name="quality refuted honest abstain",
            dossier=_dossier(run=_run("00000000-0000-0000-0000-000000000002", "transform")),
            expected_cause="upstream_spec_change",
            expect_confident=False,
        ),
        EvalCase(
            name="drift beats refuted quality run",
            dossier=_dossier(
                run=_run("00000000-0000-0000-0000-000000000003", "transform"),
                impact_drifted=True,
            ),
            expected_cause="lineage_drift",
            expect_confident=True,
        ),
        EvalCase(
            name="no run no drift abstains",
            dossier=_dossier(run=None),
            expected_cause="upstream_spec_change",
            expect_confident=False,
        ),
        EvalCase(
            name="quality gate with drift decoy",
            dossier=_dossier(
                run=_run("00000000-0000-0000-0000-000000000004", "quality:not_null"),
                impact_drifted=True,
            ),
            expected_cause="quality_gate_failure",
            expect_confident=True,
        ),
        EvalCase(
            name="quality freshness failure",
            dossier=_dossier(run=_run("00000000-0000-0000-0000-000000000005", "quality:freshness")),
            expected_cause="quality_gate_failure",
            expect_confident=True,
        ),
        EvalCase(
            name="lineage drift missing run",
            dossier=_dossier(
                run=None,
                impact_drifted=True,
                live_impacted=frozenset({"mart.orders", "mart.revenue"}),
            ),
            expected_cause="lineage_drift",
            expect_confident=True,
        ),
        EvalCase(
            name="quality volume failure",
            dossier=_dossier(run=_run("00000000-0000-0000-0000-000000000006", "quality:volume")),
            expected_cause="quality_gate_failure",
            expect_confident=True,
        ),
        EvalCase(
            name="quality accepted despite nonquality sibling",
            dossier=_dossier(
                run=_run(
                    "00000000-0000-0000-0000-000000000007",
                    "transform",
                    "quality:accepted_values",
                )
            ),
            expected_cause="quality_gate_failure",
            expect_confident=True,
        ),
    )


def _dossier(
    *,
    run: RunView | None,
    impact_drifted: bool = False,
    live_impacted: frozenset[str] = frozenset({"mart.orders"}),
) -> IncidentDossier:
    return IncidentDossier(
        subject="raw.orders",
        pipeline_id=PIPELINE_ID,
        team="revenue",
        owner="data-oncall@example.com",
        live_impacted=live_impacted,
        impacted_owners=(
            DatasetOwner(
                dataset="mart.orders",
                team="analytics",
                owner="analytics-oncall@example.com",
            ),
        ),
        failing_run=run,
        spec_version_id=SPEC_VERSION_ID,
        impact_drifted=impact_drifted,
        gaps=(SPEC_DIFF_GAP,),
    )


def _run(run_id: str, *failed_steps: str) -> RunView:
    return RunView(
        run_id=UUID(run_id),
        status="failed",
        failed_steps=failed_steps,
    )
