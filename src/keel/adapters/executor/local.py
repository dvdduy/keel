from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from keel.application.execution.plan import ExecutionPlan
from keel.application.execution.topology import topological_order
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.step_handler import Compensation, StepHandler
from keel.domain.run import Run, RunStep


@dataclass
class LocalExecutor:
    runs: RunRepository
    handler: StepHandler
    clock: Callable[[], datetime]

    def execute(
        self, pipeline_id: UUID, plan: ExecutionPlan, *, watermark: str | None = None
    ) -> Run:
        ordered_steps = topological_order(plan)
        compensations: list[Compensation] = []

        run = Run(
            id=uuid4(),
            pipeline_id=pipeline_id,
            created_at=self.clock(),
            watermark=watermark,
        )
        run.start(self.clock())

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

            try:
                compensation = self.handler.run(plan_step)
            except Exception:
                run_step.fail()
                self._rollback(compensations)
                run.fail(self.clock())
                self.runs.add(run)
                return run

            run_step.succeed()
            compensations.append(compensation)

        run.succeed(self.clock())
        self.runs.add(run)
        return run

    @staticmethod
    def _rollback(compensations: list[Compensation]) -> None:
        for compensate in reversed(compensations):
            try:
                compensate()
            except Exception:
                """
                The pass is intentional here: rollback is best-effort and exhaustive.
                A failed undo must not prevent earlier steps from being undone.
                """
                pass
