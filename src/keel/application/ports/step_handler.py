from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from keel.application.execution.plan import PlanStep

Compensation = Callable[[], None]


class StepHandler(Protocol):
    def run(self, step: PlanStep, *, run_id: UUID) -> Compensation:
        """Execute one plan step and return a compensation for its side effects.

        Raise to signal step failure. If this method raises, the failed step itself
        does not produce a compensation.
        """
        ...
