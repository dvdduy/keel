from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from keel.application.specs.models import PipelineSpec


def canonical_spec_json(spec: PipelineSpec) -> str:
    """Return the deterministic JSON preimage used for spec identity.

    Identity is based on the validated, defaults-resolved meaning of the spec,
    not the original YAML bytes."""

    return json.dumps(
        spec.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def spec_content_hash(spec: PipelineSpec) -> str:
    """Return the SHA-256 content id for a validated pipeline spec."""

    return content_sha256(canonical_spec_json(spec))


@dataclass(frozen=True)
class SpecVersion:
    version_id: UUID
    pipeline_id: UUID
    spec_id: str
    parent_id: UUID | None
    content: str
    created_at: datetime
    breaking_override: bool = False
