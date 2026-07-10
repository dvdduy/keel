from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TypeVar

import pytest

from keel.application.agent.authorization import (
    ActionEffect,
    AgentAction,
    Approval,
    ApprovalRequired,
    authorize,
)
from keel.application.agent.diagnose import Diagnosis, Hypothesis, HypothesisStatus
from keel.application.agent.guardrails import (
    enforce_narration,
    redact_for_narration,
    redact_pii,
)
from keel.application.agent.runbook import narrate_runbook


T = TypeVar("T")


class GroundedNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        return replace(
            diagnosis,
            runbook=tuple(f"Operator note: {line}" for line in diagnosis.runbook),
        )


class DroppingEvidenceNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        return replace(
            diagnosis,
            runbook=(
                "Definitely confirmed: investigate the failed quality gate.",
                f"Operator note: {diagnosis.runbook[1]}",
            ),
        )


class OverreachingNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        changed_hypotheses = tuple(
            replace(hypothesis, status=HypothesisStatus.CONFIRMED)
            for hypothesis in diagnosis.hypotheses
        )
        return Diagnosis(
            subject="changed.subject",
            hypotheses=changed_hypotheses,
            runbook=tuple(f"Operator note: {line}" for line in diagnosis.runbook),
        )


class ShortNarrator:
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        return replace(diagnosis, runbook=diagnosis.runbook[:1])


class SpyNarrator:
    seen: Diagnosis | None

    def __init__(self) -> None:
        self.seen = None

    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis:
        self.seen = diagnosis
        return diagnosis


def _run(coro) -> T:
    return asyncio.run(coro)


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        subject="raw.orders",
        hypotheses=(
            Hypothesis(
                kind="quality_gate_failure",
                summary="Quality gate failed for owner alice@example.com.",
                status=HypothesisStatus.CONFIRMED,
                evidence=(
                    "run bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb status failed",
                    "owner alice@example.com saw failed quality step quality:not_null",
                ),
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
            (
                "Investigate the failed quality gate; evidence: "
                "run bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb status failed; "
                "owner alice@example.com saw failed quality step quality:not_null."
            ),
            (
                "Could not verify an upstream spec change: correlated changes unavailable: "
                "no spec history/diff read endpoint - compare recent spec versions manually."
            ),
        ),
    )


def test_narrator_may_reword_grounded_lines() -> None:
    diagnosis = redact_for_narration(_diagnosis())

    narrated = enforce_narration(
        diagnosis,
        replace(
            diagnosis,
            runbook=tuple(f"Operator note: {line}" for line in diagnosis.runbook),
        ),
    )

    assert narrated.runbook == tuple(f"Operator note: {line}" for line in diagnosis.runbook)


def test_narrator_line_dropping_evidence_falls_back_to_deterministic() -> None:
    diagnosis = redact_for_narration(_diagnosis())

    narrated = _run(narrate_runbook(_diagnosis(), DroppingEvidenceNarrator()))

    assert narrated.runbook[0] == diagnosis.runbook[0]
    assert narrated.runbook[1] == f"Operator note: {diagnosis.runbook[1]}"


def test_narrator_cannot_change_hypotheses_or_subject() -> None:
    diagnosis = redact_for_narration(_diagnosis())

    narrated = _run(narrate_runbook(_diagnosis(), OverreachingNarrator()))

    assert narrated.subject == diagnosis.subject
    assert narrated.hypotheses == diagnosis.hypotheses


def test_length_mismatch_discards_narrator_runbook() -> None:
    diagnosis = redact_for_narration(_diagnosis())

    narrated = _run(narrate_runbook(_diagnosis(), ShortNarrator()))

    assert narrated.runbook == diagnosis.runbook


def test_redact_pii_masks_email_tokens() -> None:
    assert redact_pii("contact alice@example.com and bob.smith+ops@example.co.uk") == (
        "contact [redacted-email] and [redacted-email]"
    )


def test_redact_for_narration_scrubs_evidence_before_narrator_sees_it() -> None:
    narrator = SpyNarrator()

    _run(narrate_runbook(_diagnosis(), narrator))

    assert narrator.seen is not None
    assert "alice@example.com" not in str(narrator.seen)
    assert "[redacted-email]" in str(narrator.seen)


def test_pii_in_original_never_reaches_final_runbook() -> None:
    narrated = _run(narrate_runbook(_diagnosis(), GroundedNarrator()))

    assert all("alice@example.com" not in line for line in narrated.runbook)
    assert any("[redacted-email]" in line for line in narrated.runbook)


def test_read_action_needs_no_approval() -> None:
    authorize(AgentAction(name="catalog_show", effect=ActionEffect.READ), None)


def test_write_action_without_approval_is_refused() -> None:
    with pytest.raises(ApprovalRequired):
        authorize(AgentAction(name="incident_ack", effect=ActionEffect.WRITE), None)


def test_write_action_with_approval_is_authorized() -> None:
    authorize(
        AgentAction(name="incident_ack", effect=ActionEffect.WRITE),
        Approval(approver="on-call"),
    )
