from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from keel.application.ports.spec_version_repo import SpecVersionRepository
from keel.application.specs.models import PipelineSpec
from keel.application.specs.versioning import SpecVersion, canonical_spec_json, content_sha256


@dataclass(frozen=True)
class SubmitResult:
    version: SpecVersion
    created: bool


@dataclass
class SubmitSpec:
    versions: SpecVersionRepository

    def submit(self, pipeline_id: UUID, spec: PipelineSpec) -> SubmitResult:
        content = canonical_spec_json(spec)
        spec_id = content_sha256(content)
        head = self.versions.head_for(pipeline_id)

        if head is not None and head.spec_id == spec_id:
            return SubmitResult(version=head, created=False)

        version = SpecVersion(
            version_id=uuid4(),
            pipeline_id=pipeline_id,
            spec_id=spec_id,
            parent_id=head.version_id if head is not None else None,
            content=canonical_spec_json(spec),
            created_at=datetime.now(UTC),
        )
        self.versions.add(version)
        return SubmitResult(version=version, created=True)
