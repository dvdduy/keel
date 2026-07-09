from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from keel.application.catalog.entry import CatalogEntry
from keel.application.specs.compatibility import BreakingChange
from keel.application.specs.diagnostics import Diagnostic
from keel.application.specs.models import ContractColumn
from keel.application.specs.versioning import SpecVersion
from keel.domain.run import Run, RunStep


class WireModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class DiagnosticOut(WireModel):
    loc: str
    message: str

    @classmethod
    def from_diagnostic(cls, diagnostic: Diagnostic) -> "DiagnosticOut":
        return cls(loc=diagnostic.loc, message=diagnostic.message)


class BreakingChangeOut(WireModel):
    kind: str
    column: str
    detail: str

    @classmethod
    def from_change(cls, change: BreakingChange) -> "BreakingChangeOut":
        return cls(kind=change.kind.value, column=change.column, detail=change.detail)


class ColumnOut(WireModel):
    name: str
    type: str
    nullable: bool

    @classmethod
    def from_column(cls, column: ContractColumn) -> "ColumnOut":
        return cls(name=column.name, type=column.type.value, nullable=column.nullable)


class SpecVersionOut(WireModel):
    version_id: UUID
    pipeline_id: UUID
    spec_id: str
    parent_id: UUID | None
    created_at: datetime
    breaking_override: bool

    @classmethod
    def from_version(cls, version: SpecVersion) -> "SpecVersionOut":
        return cls(
            version_id=version.version_id,
            pipeline_id=version.pipeline_id,
            spec_id=version.spec_id,
            parent_id=version.parent_id,
            created_at=version.created_at,
            breaking_override=version.breaking_override,
        )


class CatalogEntryOut(WireModel):
    dataset: str
    pipeline_name: str
    team: str
    owner: str
    columns: tuple[ColumnOut, ...]
    pipeline_id: UUID
    source_spec_id: str
    updated_at: datetime

    @classmethod
    def from_entry(cls, entry: CatalogEntry) -> "CatalogEntryOut":
        return cls(
            dataset=entry.dataset,
            pipeline_name=entry.pipeline_name,
            team=entry.team,
            owner=entry.owner,
            columns=tuple(ColumnOut.from_column(column) for column in entry.columns),
            pipeline_id=entry.pipeline_id,
            source_spec_id=entry.source_spec_id,
            updated_at=entry.updated_at,
        )


class RunStepOut(WireModel):
    id: UUID
    run_id: UUID
    name: str
    sequence: int
    created_at: datetime
    status: str

    @classmethod
    def from_step(cls, step: RunStep) -> "RunStepOut":
        return cls(
            id=step.id,
            run_id=step.run_id,
            name=step.name,
            sequence=step.sequence,
            created_at=step.created_at,
            status=step.status.value,
        )


class RunOut(WireModel):
    id: UUID
    pipeline_id: UUID
    created_at: datetime
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    watermark: str | None
    steps: tuple[RunStepOut, ...]

    @classmethod
    def from_run(cls, run: Run) -> "RunOut":
        return cls(
            id=run.id,
            pipeline_id=run.pipeline_id,
            created_at=run.created_at,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            watermark=run.watermark,
            steps=tuple(RunStepOut.from_step(step) for step in run.steps),
        )


class LineageImpactOut(WireModel):
    dataset: str
    impacted: tuple[str, ...]
