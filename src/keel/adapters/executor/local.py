from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from keel.application.execution.plan import ExecutionPlan
from keel.application.execution.topology import topological_order
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.step_handler import StepHandler
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
                self.handler.run(plan_step)
            except Exception:
                run_step.fail()
                run.fail(self.clock())
                self.runs.add(run)
                return run

            run_step.succeed()

        run.succeed(self.clock())
        self.runs.add(run)
        return run
