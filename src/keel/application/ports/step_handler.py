from __future__ import annotations
from typing import Protocol

from keel.application.execution.plan import PlanStep


class StepHandler(Protocol):
    def run(self, step: PlanStep) -> None:
        """Execute one plan step.

        Raise any exception to signal step failure.
        """
        ...
