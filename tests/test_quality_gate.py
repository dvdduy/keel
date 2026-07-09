from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from keel.application.quality.checks import CheckResult, CheckStatus
from keel.application.quality.gate import GateDecision, apply_gate, decide_gate
from keel.application.quality.results import QualityResult
from keel.application.specs.models import QualityCheckType


@dataclass
class FakeQualityResultRepository:
    added: list[QualityResult] = field(default_factory=list)

    def add(self, result: QualityResult) -> None:
        self.added.append(result)

    def for_run(self, run_id: UUID) -> tuple[QualityResult, ...]:
        return tuple(result for result in self.added if result.run_id == run_id)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def _result(
    status: CheckStatus,
    *,
    violations: int | None,
    detail: str = "detail",
) -> CheckResult:
    return CheckResult(
        check_type=QualityCheckType.UNIQUE,
        column="order_id",
        status=status,
        detail=detail,
        violations=violations,
    )


def test_passed_check_records_result_and_proceeds() -> None:
    run_id = uuid4()
    repo = FakeQualityResultRepository()

    decision = apply_gate(
        run_id=run_id,
        result=_result(CheckStatus.PASSED, violations=0),
        results=repo,
        clock=FakeClock(),
    )

    assert decision == GateDecision.PROCEED

    recorded = repo.for_run(run_id)
    assert len(recorded) == 1
    assert recorded[0].run_id == run_id
    assert recorded[0].check_type == QualityCheckType.UNIQUE
    assert recorded[0].column == "order_id"
    assert recorded[0].status == CheckStatus.PASSED
    assert recorded[0].violations == 0


def test_failed_check_records_violations_and_blocks() -> None:
    run_id = uuid4()
    repo = FakeQualityResultRepository()

    decision = apply_gate(
        run_id=run_id,
        result=_result(CheckStatus.FAILED, violations=1, detail="duplicate order_id"),
        results=repo,
        clock=FakeClock(),
    )

    assert decision == GateDecision.BLOCK

    recorded = repo.for_run(run_id)
    assert len(recorded) == 1
    assert recorded[0].status == CheckStatus.FAILED
    assert recorded[0].violations == 1
    assert recorded[0].detail == "duplicate order_id"


def test_unknown_check_records_and_blocks() -> None:
    run_id = uuid4()
    repo = FakeQualityResultRepository()

    decision = apply_gate(
        run_id=run_id,
        result=_result(CheckStatus.UNKNOWN, violations=None, detail="column missing"),
        results=repo,
        clock=FakeClock(),
    )

    assert decision == GateDecision.BLOCK

    recorded = repo.for_run(run_id)
    assert len(recorded) == 1
    assert recorded[0].status == CheckStatus.UNKNOWN
    assert recorded[0].violations is None
    assert recorded[0].detail == "column missing"


def test_gate_records_every_status_a_monitor_would() -> None:
    run_id = uuid4()
    repo = FakeQualityResultRepository()
    clock = FakeClock()

    statuses = (
        CheckStatus.PASSED,
        CheckStatus.FAILED,
        CheckStatus.UNKNOWN,
    )

    decisions = [
        apply_gate(
            run_id=run_id,
            result=_result(
                status,
                violations=0 if status is CheckStatus.PASSED else None,
            ),
            results=repo,
            clock=clock,
        )
        for status in statuses
    ]

    assert decisions == [
        GateDecision.PROCEED,
        GateDecision.BLOCK,
        GateDecision.BLOCK,
    ]
    assert tuple(result.status for result in repo.for_run(run_id)) == statuses


def test_decide_gate_fails_closed_for_unknown() -> None:
    assert decide_gate(_result(CheckStatus.UNKNOWN, violations=None)) == GateDecision.BLOCK
