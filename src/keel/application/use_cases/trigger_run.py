from dataclasses import dataclass

from keel.application.execution.plan import ExecutionPlan
from keel.application.ports.executor import PipelineExecutor
from keel.application.ports.run_repo import RunRepository
from keel.domain.run import Run, RunKey, is_replayable


@dataclass(frozen=True)
class TriggerResult:
    run: Run
    executed: bool


@dataclass
class TriggerRun:
    runs: RunRepository
    executor: PipelineExecutor

    def trigger(self, key: RunKey, plan: ExecutionPlan) -> TriggerResult:
        existing = self.runs.latest_for_key(key)

        if existing is not None and not is_replayable(existing):
            return TriggerResult(run=existing, executed=False)

        run = self.executor.execute(key.pipeline_id, plan, watermark=key.watermark)

        return TriggerResult(run=run, executed=True)
