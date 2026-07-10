from __future__ import annotations

from pathlib import Path

from demo.breaking_change import InMemorySpecVersionRepository, run_demo
from keel.application.quality.checks import CheckStatus
from keel.application.slo.model import SloStatus
from keel.domain.run import RunStatus


def test_breaking_change_demo_invariants(tmp_path: Path) -> None:
    result = run_demo(workspace_factory=lambda: _ExistingTemporaryDirectory(tmp_path))

    assert result.rejection.head_unchanged is True
    assert [change.column for change in result.rejection.changes] == ["amount"]
    assert result.override.audited is True

    assert result.containment.run.status == RunStatus.FAILED
    assert result.containment.quality_results[0].status == CheckStatus.UNKNOWN
    assert result.containment.evaluation_status == SloStatus.BREACHING
    assert len(result.containment.groups) == 1

    group = result.containment.groups[0]
    assert [incident.subject for incident in group.roots] == ["raw.orders"]
    assert len(group.correlated) == len(result.graph.downstream)
    assert result.containment.diagnosis.subject == "raw.orders"
    assert result.containment.top_hypothesis_kind == "quality_gate_failure"


def test_demo_uses_an_in_memory_spec_repository() -> None:
    repository = InMemorySpecVersionRepository()

    assert repository.heads() == ()


class _ExistingTemporaryDirectory:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        return str(self.path)

    def __exit__(self, *_args: object) -> None:
        return None
