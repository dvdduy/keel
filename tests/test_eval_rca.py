from __future__ import annotations

from keel.application.agent.diagnose import Diagnosis, Hypothesis, HypothesisStatus, diagnose

from evals.rca.cases import cases
from evals.rca.run import MAX_FALSE_POSITIVE_RATE, MIN_TOP1_ACCURACY
from evals.rca.score import EvalCase, aggregate, score_case


def test_rca_eval_meets_thresholds() -> None:
    results = tuple(score_case(case, diagnose(case.dossier)) for case in cases())
    report = aggregate(results)

    assert report.n >= 6
    assert report.top1_accuracy >= MIN_TOP1_ACCURACY
    assert report.false_positive_rate <= MAX_FALSE_POSITIVE_RATE


def test_scorer_counts_top1_correct() -> None:
    result = score_case(
        _case(expected_cause="quality_gate_failure", expect_confident=True),
        _diagnosis(
            _hypothesis("quality_gate_failure", HypothesisStatus.CONFIRMED, 1),
            _hypothesis("upstream_spec_change", HypothesisStatus.UNVERIFIED, 2),
        ),
    )

    assert result.correct is True
    assert result.top3_hit is True
    assert result.false_positive is False
    assert result.abstained is False


def test_scorer_flags_false_positive() -> None:
    result = score_case(
        _case(expected_cause="quality_gate_failure", expect_confident=True),
        _diagnosis(
            _hypothesis("quality_gate_failure", HypothesisStatus.CONFIRMED, 1),
            _hypothesis("lineage_drift", HypothesisStatus.CONFIRMED, 2),
        ),
    )

    assert result.correct is True
    assert result.false_positive is True


def test_scorer_credits_honest_abstention() -> None:
    result = score_case(
        _case(expected_cause="upstream_spec_change", expect_confident=False),
        _diagnosis(
            _hypothesis("upstream_spec_change", HypothesisStatus.UNVERIFIED, 1),
            _hypothesis("quality_gate_failure", HypothesisStatus.REFUTED, 2),
        ),
    )

    assert result.correct is True
    assert result.false_positive is False
    assert result.abstained is True


def test_scorer_top3_hit_when_confirmed_not_rank1() -> None:
    result = score_case(
        _case(expected_cause="lineage_drift", expect_confident=True),
        _diagnosis(
            _hypothesis("quality_gate_failure", HypothesisStatus.CONFIRMED, 1),
            _hypothesis("lineage_drift", HypothesisStatus.CONFIRMED, 2),
        ),
    )

    assert result.correct is False
    assert result.top3_hit is True
    assert result.false_positive is True


def _case(*, expected_cause: str, expect_confident: bool) -> EvalCase:
    return EvalCase(
        name="scorer fixture",
        dossier=cases()[0].dossier,
        expected_cause=expected_cause,
        expect_confident=expect_confident,
    )


def _diagnosis(*hypotheses: Hypothesis) -> Diagnosis:
    return Diagnosis(subject="raw.orders", hypotheses=hypotheses, runbook=())


def _hypothesis(kind: str, status: HypothesisStatus, rank: int) -> Hypothesis:
    return Hypothesis(
        kind=kind,
        summary=f"{kind} summary",
        status=status,
        evidence=(f"{kind} evidence",),
        rank=rank,
    )
