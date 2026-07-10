from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TypeVar

from keel.application.agent.diagnose import Diagnosis, Hypothesis, HypothesisStatus
from keel.application.agent.runbook import narrate_runbook


T = TypeVar("T")


class DeterministicRunbookNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        return replace(
            diagnosis,
            runbook=tuple(f"Operator note: {line}" for line in diagnosis.runbook),
        )


class OverreachingRunbookNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        rewritten = tuple(
            replace(hypothesis, status=HypothesisStatus.CONFIRMED)
            for hypothesis in diagnosis.hypotheses
        )
        return replace(
            diagnosis,
            hypotheses=rewritten,
            runbook=tuple(f"Definitely confirmed: {line}" for line in diagnosis.runbook),
        )


def _run(coro) -> T:
    return asyncio.run(coro)


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        subject="raw.orders",
        hypotheses=(
            Hypothesis(
                kind="quality_gate_failure",
                summary="The incident is explained by a failed quality gate.",
                status=HypothesisStatus.CONFIRMED,
                evidence=("run bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb status failed",),
                rank=1,
            ),
            Hypothesis(
                kind="upstream_spec_change",
                summary="An upstream spec change could have contributed to the breach.",
                status=HypothesisStatus.UNVERIFIED,
                evidence=("correlated changes unavailable: no spec history/diff read endpoint",),
                rank=2,
            ),
        ),
        runbook=(
            "Investigate the failed quality gate; evidence: run status failed.",
            (
                "Could not verify an upstream spec change: no spec history/diff read endpoint "
                "- compare recent spec versions manually."
            ),
        ),
    )


def test_narrator_may_reword_runbook() -> None:
    diagnosis = _diagnosis()

    narrated = _run(narrate_runbook(diagnosis, DeterministicRunbookNarrator()))

    assert narrated.hypotheses == diagnosis.hypotheses
    assert narrated.runbook == tuple(f"Operator note: {line}" for line in diagnosis.runbook)


def test_narrator_cannot_restatus_or_replace_hypotheses() -> None:
    diagnosis = _diagnosis()

    narrated = _run(narrate_runbook(diagnosis, OverreachingRunbookNarrator()))

    assert narrated.hypotheses == diagnosis.hypotheses
    assert {
        hypothesis.kind
        for hypothesis in narrated.hypotheses
        if hypothesis.status == HypothesisStatus.CONFIRMED
    } == {"quality_gate_failure"}
