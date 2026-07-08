from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timezone

from keel.application.ports.run_repo import RunRepository
from keel.application.ports.warehouse import WarehouseAdapter
from keel.domain.run import Run, RunStep, RunStatus


@dataclass
class RunPipeline:
    runs: RunRepository
    warehouse: WarehouseAdapter

    def execute(self, pipeline_id: UUID, source: Path, destination: str) -> Run:
        now = datetime.now(timezone.utc)

        self.warehouse.ingest_csv(destination, source)

        run = Run(
            id=uuid4(),
            created_at=now,
            pipeline_id=pipeline_id,
            status=RunStatus.RUNNING,
            started_at=now,
            finished_at=now,
        )

        step = RunStep(
            id=uuid4(),
            run_id=run.id,
            created_at=now,
            name="ingest",
            status=RunStatus.SUCCESS,
            sequence=1,
        )
        run.status = RunStatus.SUCCESS
        run.steps = [step]

        self.runs.add(run)
        return run
