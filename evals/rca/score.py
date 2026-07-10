from __future__ import annotations

from dataclasses import dataclass, field

from keel.application.agent.diagnose import Diagnosis, HypothesisStatus
from keel.application.agent.dossier import IncidentDossier


@dataclass(frozen=True)
class EvalCase:
    name: str
    dossier: IncidentDossier
    expected_cause: str
    expect_confident: bool


@dataclass(frozen=True)
class CaseResult:
    name: str
    correct: bool
    top3_hit: bool
    false_positive: bool
    abstained: bool
    _expect_confident: bool = field(default=True, repr=False, compare=False)


@dataclass(frozen=True)
class EvalReport:
    n: int
    top1_accuracy: float
    top3_accuracy: float
    false_positive_rate: float
    abstention_rate: float


def score_case(case: EvalCase, diagnosis: Diagnosis) -> CaseResult:
    confirmed = tuple(
        hypothesis
        for hypothesis in diagnosis.hypotheses
        if hypothesis.status == HypothesisStatus.CONFIRMED
    )
    abstained = not confirmed
    top1 = diagnosis.hypotheses[0] if diagnosis.hypotheses else None

    if case.expect_confident:
        correct = (
            top1 is not None
            and top1.kind == case.expected_cause
            and top1.status == HypothesisStatus.CONFIRMED
        )
        top3_hit = any(
            hypothesis.kind == case.expected_cause for hypothesis in diagnosis.hypotheses[:3]
        )
        false_positive = any(hypothesis.kind != case.expected_cause for hypothesis in confirmed)
    else:
        correct = abstained
        top3_hit = False
        false_positive = bool(confirmed)

    return CaseResult(
        name=case.name,
        correct=correct,
        top3_hit=top3_hit,
        false_positive=false_positive,
        abstained=abstained,
        _expect_confident=case.expect_confident,
    )


def aggregate(results: tuple[CaseResult, ...]) -> EvalReport:
    confident_results = tuple(result for result in results if result._expect_confident)
    return EvalReport(
        n=len(results),
        top1_accuracy=_mean(tuple(result.correct for result in results)),
        top3_accuracy=_mean(tuple(result.top3_hit for result in confident_results)),
        false_positive_rate=_mean(tuple(result.false_positive for result in results)),
        abstention_rate=_mean(tuple(result.abstained for result in results)),
    )


def _mean(values: tuple[bool, ...]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value) / len(values)
