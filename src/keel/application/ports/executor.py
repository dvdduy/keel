from __future__ import annotations

from typing import Protocol
from uuid import UUID

from keel.application.execution.plan import ExecutionPlan
from keel.domain.run import Run


class PipelineExecutor(Protocol):
    def execute(
        self,
        pipeline_id: UUID,
        plan: ExecutionPlan,
        *,
        watermark: str | None = None,
    ) -> Run:
        """Execute a compiled plan for a pipeline, returning the resulting Run."""
        ...
