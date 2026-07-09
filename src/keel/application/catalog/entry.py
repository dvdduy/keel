from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from keel.application.specs.models import ContractColumn, PipelineSpec
from keel.application.specs.versioning import SpecVersion


@dataclass(frozen=True)
class CatalogEntry:
    dataset: str
    pipeline_name: str
    team: str
    owner: str
    columns: tuple[ContractColumn, ...]
    pipeline_id: UUID
    source_spec_id: str
    updated_at: datetime


def project_catalog_entry(version: SpecVersion) -> CatalogEntry:
    spec = PipelineSpec.model_validate_json(version.content)
    return CatalogEntry(
        dataset=spec.destination,
        pipeline_name=spec.name,
        team=spec.team,
        owner=spec.owner,
        columns=spec.contract,
        pipeline_id=version.pipeline_id,
        source_spec_id=version.spec_id,
        updated_at=version.created_at,
    )
