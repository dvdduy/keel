from __future__ import annotations

from typing import Protocol

from keel.domain.run import Run, RunStep


class RunObserver(Protocol):
    def run_started(self, run: Run) -> None: ...
    def step_started(self, run: Run, step: RunStep) -> None: ...
    def step_finished(self, run: Run, step: RunStep) -> None: ...
    def run_finished(self, run: Run) -> None: ...


class NullObserver:
    def run_started(self, run: Run) -> None:
        pass

    def step_started(self, run: Run, step: RunStep) -> None:
        pass

    def step_finished(self, run: Run, step: RunStep) -> None:
        pass

    def run_finished(self, run: Run) -> None:
        pass
