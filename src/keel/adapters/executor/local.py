from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from keel.application.execution.plan import ExecutionPlan
from keel.application.execution.topology import topological_order
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.step_handler import Compensation, StepHandler
from keel.application.ports.telemetry import NullObserver, RunObserver
from keel.domain.run import Run, RunStep

logger = logging.getLogger(__name__)


@dataclass
class LocalExecutor:
    runs: RunRepository
    handler: StepHandler
    clock: Callable[[], datetime]
    observer: RunObserver = field(default_factory=NullObserver)

    def execute(
        self, pipeline_id: UUID, plan: ExecutionPlan, *, watermark: str | None = None
    ) -> Run:
        ordered_steps = topological_order(plan)
        compensations: list[tuple[str, Compensation]] = []

        run = Run(
            id=uuid4(),
            pipeline_id=pipeline_id,
            created_at=self.clock(),
            watermark=watermark,
        )
        run.start(self.clock())
        self.observer.run_started(run)

        for sequence, plan_step in enumerate(ordered_steps, start=1):
            run_step = RunStep(
                id=uuid4(),
                run_id=run.id,
                name=plan_step.key,
                sequence=sequence,
                created_at=self.clock(),
            )
            run.add_step(run_step)
            run_step.start()
            self.observer.step_started(run, run_step)

            failed = False
            compensation: Compensation | None = None
            try:
                compensation = self.handler.run(run_id=run.id, step=plan_step)
            except Exception:
                failed = True
                run_step.fail()
            else:
                run_step.succeed()
            finally:
                self.observer.step_finished(run, run_step)

            if failed:
                self._rollback(compensations)
                run.fail(self.clock())
                self.observer.run_finished(run)
                self.runs.add(run)
                return run

            if compensation is None:
                raise RuntimeError(f"step {plan_step.key!r} completed without compensation")
            compensations.append((plan_step.key, compensation))

        run.succeed(self.clock())
        self.observer.run_finished(run)
        self.runs.add(run)
        return run

    @staticmethod
    def _rollback(compensations: list[tuple[str, Compensation]]) -> None:
        for step_key, compensate in reversed(compensations):
            try:
                compensate()
            except Exception:
                logger.exception(
                    "Compensation failed while rolling back step %r",
                    step_key,
                )
                # Rollback is best-effort and exhaustive: one failed compensation
                # must not prevent earlier successful steps from being undone.
