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
    column: str = "order_id",
    violations: int | None = None,
    detail: str = "detail",
) -> CheckResult:
    return CheckResult(
        check_type=QualityCheckType.UNIQUE,
        column=column,
        status=status,
        detail=detail,
        violations=violations,
    )


def test_gate_proceeds_when_all_pass() -> None:
    decision = decide_gate(
        [
            _result(CheckStatus.PASSED, column="order_id", violations=0),
            _result(CheckStatus.PASSED, column="customer_id", violations=0),
        ]
    )

    assert decision == GateDecision.PROCEED


def test_gate_blocks_when_any_fails() -> None:
    decision = decide_gate(
        [
            _result(CheckStatus.PASSED, column="order_id", violations=0),
            _result(CheckStatus.FAILED, column="customer_id", violations=1),
        ]
    )

    assert decision == GateDecision.BLOCK


def test_gate_blocks_when_any_unknown() -> None:
    decision = decide_gate(
        [
            _result(CheckStatus.PASSED, column="order_id", violations=0),
            _result(CheckStatus.UNKNOWN, column="customer_id", violations=None),
        ]
    )

    assert decision == GateDecision.BLOCK


def test_apply_gate_records_all_before_deciding() -> None:
    run_id = uuid4()
    repo = FakeQualityResultRepository()

    decision = apply_gate(
        run_id=run_id,
        results=[
            _result(CheckStatus.FAILED, column="order_id", violations=1),
            _result(CheckStatus.PASSED, column="customer_id", violations=0),
            _result(CheckStatus.FAILED, column="amount", violations=2),
        ],
        repository=repo,
        clock=FakeClock(),
    )

    recorded = repo.for_run(run_id)

    assert decision == GateDecision.BLOCK
    assert len(recorded) == 3
    assert [result.status for result in recorded] == [
        CheckStatus.FAILED,
        CheckStatus.PASSED,
        CheckStatus.FAILED,
    ]
