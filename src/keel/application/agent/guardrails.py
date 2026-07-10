from __future__ import annotations

import re
from dataclasses import replace

from keel.application.agent.diagnose import Diagnosis, Hypothesis


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_EMAIL_MASK = "[redacted-email]"


def redact_pii(text: str) -> str:
    return _EMAIL_RE.sub(_EMAIL_MASK, text)


def redact_for_narration(diagnosis: Diagnosis) -> Diagnosis:
    return replace(
        diagnosis,
        hypotheses=tuple(_redact_hypothesis(hypothesis) for hypothesis in diagnosis.hypotheses),
        runbook=tuple(redact_pii(line) for line in diagnosis.runbook),
    )


def enforce_narration(original: Diagnosis, narrated: Diagnosis) -> Diagnosis:
    if len(narrated.runbook) != len(original.runbook):
        return original

    guarded_lines = tuple(
        _guard_runbook_line(original, narrated.runbook[index], index)
        for index in range(len(original.runbook))
    )
    return replace(original, runbook=guarded_lines)


def _redact_hypothesis(hypothesis: Hypothesis) -> Hypothesis:
    return replace(
        hypothesis,
        summary=redact_pii(hypothesis.summary),
        evidence=tuple(redact_pii(evidence) for evidence in hypothesis.evidence),
    )


def _guard_runbook_line(original: Diagnosis, narrated_line: str, index: int) -> str:
    if index >= len(original.hypotheses):
        return original.runbook[index]

    evidence = original.hypotheses[index].evidence
    if all(anchor in narrated_line for anchor in evidence):
        return narrated_line
    return original.runbook[index]
