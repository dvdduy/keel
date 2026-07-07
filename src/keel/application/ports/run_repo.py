from typing import Protocol
from uuid import UUID
from keel.domain.run import Run


class RunRepository(Protocol):
    def add(self, run: Run) -> None: ...
    def get(self, run_id: UUID) -> Run | None: ...
