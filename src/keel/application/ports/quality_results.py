from __future__ import annotations

from typing import Protocol
from uuid import UUID

from keel.application.quality.results import QualityResult


class QualityResultRepository(Protocol):
    def add(self, result: QualityResult) -> None: ...

    def for_run(self, run_id: UUID) -> tuple[QualityResult, ...]: ...
