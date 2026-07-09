from __future__ import annotations

from typing import Protocol
from uuid import UUID

from keel.application.specs.versioning import SpecVersion


class SpecVersionRepository(Protocol):
    def head_for(self, pipeline_id: UUID) -> SpecVersion | None: ...

    def heads(self) -> tuple[SpecVersion, ...]: ...

    def add(self, version: SpecVersion) -> None: ...
