from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from keel.application.ports.spec_version_repo import SpecVersionRepository
from keel.application.ports.catalog import DatasetCatalog
from keel.application.catalog.entry import project_catalog_entry
from keel.application.specs.compatibility import (
    IncompatibleSpecError,
    check_compatibility,
)
from keel.application.specs.models import PipelineSpec
from keel.application.specs.versioning import (
    SpecVersion,
    canonical_spec_json,
    content_sha256,
)


@dataclass(frozen=True)
class SubmitResult:
    version: SpecVersion
    created: bool


@dataclass
class SubmitSpec:
    versions: SpecVersionRepository
    catalog: DatasetCatalog | None = None

    def submit(
        self,
        pipeline_id: UUID,
        spec: PipelineSpec,
        *,
        allow_breaking: bool = False,
    ) -> SubmitResult:
        content = canonical_spec_json(spec)
        spec_id = content_sha256(content)
        head = self.versions.head_for(pipeline_id)

        if head is not None and head.spec_id == spec_id:
            if self.catalog is not None:
                self.catalog.upsert(project_catalog_entry(head))
            return SubmitResult(version=head, created=False)

        breaking_override = False

        if head is not None:
            previous = PipelineSpec.model_validate_json(head.content)
            report = check_compatibility(previous, spec)

            if not report.compatible:
                if not allow_breaking:
                    raise IncompatibleSpecError(report)

                breaking_override = True

        version = SpecVersion(
            version_id=uuid4(),
            pipeline_id=pipeline_id,
            spec_id=spec_id,
            parent_id=head.version_id if head is not None else None,
            content=content,
            created_at=datetime.now(UTC),
            breaking_override=breaking_override,
        )

        self.versions.add(version)
        if self.catalog is not None:
            self.catalog.upsert(project_catalog_entry(version))

        return SubmitResult(version=version, created=True)
