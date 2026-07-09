from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from keel.application.agent.dossier import DatasetOwner, RunView


class PlatformReader(Protocol):
    async def lineage_impact(self, dataset: str) -> frozenset[str]: ...

    async def catalog_show(self, dataset: str) -> DatasetOwner | None: ...

    async def run_show(self, run_id: UUID) -> RunView | None: ...

    async def spec_head(self, pipeline_id: UUID) -> UUID | None: ...
