from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from keel.application.agent.dossier import IncidentDossier, RunView


class HypothesisStatus(StrEnum):
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Hypothesis:
    kind: str
    summary: str
    status: HypothesisStatus
    evidence: tuple[str, ...]
    rank: int


@dataclass(frozen=True)
class Diagnosis:
    subject: str
    hypotheses: tuple[Hypothesis, ...]
    runbook: tuple[str, ...]


def diagnose(dossier: IncidentDossier) -> Diagnosis:
    ranked = tuple(
        replace(hypothesis, rank=rank)
        for rank, hypothesis in enumerate(
            sorted(_hypotheses(dossier), key=_rank_key),
            start=1,
        )
    )
    return Diagnosis(
        subject=dossier.subject,
        hypotheses=ranked,
        runbook=tuple(_runbook_line(hypothesis) for hypothesis in ranked),
    )


def _hypotheses(dossier: IncidentDossier) -> tuple[Hypothesis, ...]:
    hypotheses: list[Hypothesis] = []

    if dossier.failing_run is not None:
        hypotheses.append(_quality_gate_failure(dossier.failing_run))

    if dossier.impact_drifted:
        hypotheses.append(_lineage_drift())

    hypotheses.append(_upstream_spec_change(dossier.gaps))
    return tuple(hypotheses)


def _quality_gate_failure(run: RunView) -> Hypothesis:
    quality_steps = tuple(step for step in run.failed_steps if step.startswith("quality:"))
    run_evidence = f"run {run.run_id} status {run.status}"

    if quality_steps:
        return Hypothesis(
            kind="quality_gate_failure",
            summary="The incident is explained by a failed quality gate in the failing run.",
            status=HypothesisStatus.CONFIRMED,
            evidence=(run_evidence,)
            + tuple(f"failed quality step {step}" for step in quality_steps),
            rank=0,
        )

    return Hypothesis(
        kind="quality_gate_failure",
        summary="The failing run did not fail at a quality gate.",
        status=HypothesisStatus.REFUTED,
        evidence=(
            run_evidence,
            f"failed steps are not quality gates: {', '.join(run.failed_steps)}",
        ),
        rank=0,
    )


def _lineage_drift() -> Hypothesis:
    return Hypothesis(
        kind="lineage_drift",
        summary="The live blast radius has drifted from the incident snapshot.",
        status=HypothesisStatus.CONFIRMED,
        evidence=("live blast radius differs from the incident snapshot",),
        rank=0,
    )


def _upstream_spec_change(gaps: tuple[str, ...]) -> Hypothesis:
    gap = next(
        (
            recorded_gap
            for recorded_gap in gaps
            if "spec history/diff read endpoint" in recorded_gap
        ),
        "correlated changes unavailable: no spec history/diff read endpoint",
    )
    return Hypothesis(
        kind="upstream_spec_change",
        summary="An upstream spec change could have contributed to the breach.",
        status=HypothesisStatus.UNVERIFIED,
        evidence=(gap,),
        rank=0,
    )


def _rank_key(hypothesis: Hypothesis) -> tuple[int, int]:
    status_order = {
        HypothesisStatus.CONFIRMED: 0,
        HypothesisStatus.UNVERIFIED: 1,
        HypothesisStatus.REFUTED: 2,
    }
    kind_order = {
        "quality_gate_failure": 0,
        "lineage_drift": 1,
        "upstream_spec_change": 2,
    }
    return (status_order[hypothesis.status], kind_order[hypothesis.kind])


def _runbook_line(hypothesis: Hypothesis) -> str:
    evidence = "; ".join(hypothesis.evidence)
    if (
        hypothesis.kind == "quality_gate_failure"
        and hypothesis.status == HypothesisStatus.CONFIRMED
    ):
        return f"Investigate the failed quality gate; evidence: {evidence}."
    if hypothesis.kind == "lineage_drift":
        return f"Use live lineage for impact and owner routing; evidence: {evidence}."
    if hypothesis.kind == "upstream_spec_change":
        return (
            "Could not verify an upstream spec change: "
            f"{evidence} - compare recent spec versions manually."
        )
    return f"Do not pursue quality gate failure as the cause; evidence: {evidence}."
