from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from keel.application.execution.plan import IngestStep, PlanStep
from keel.application.ports.step_handler import Compensation
from keel.application.ports.warehouse import WarehouseAdapter


@dataclass
class DuckDbStepHandler:
    warehouse: WarehouseAdapter

    def run(self, step: PlanStep) -> Compensation:
        match step:
            case IngestStep():
                self.warehouse.ingest_csv(step.destination, Path(step.source_path))
                return lambda: self.warehouse.drop_table(step.destination)

            case _:
                raise NotImplementedError(f"no DuckDB handler for step {step.key!r}")
