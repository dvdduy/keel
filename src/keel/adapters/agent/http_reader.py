from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import httpx

from keel.adapters.control_plane.read_only_client import ReadOnlyControlPlane
from keel.application.agent.dossier import DatasetOwner, RunView
from keel.application.ports.platform_reader import PlatformReader


JsonObject = dict[str, Any]


class HttpPlatformReader(PlatformReader):
    def __init__(self, control_plane: ReadOnlyControlPlane) -> None:
        self._control_plane = control_plane

    async def lineage_impact(self, dataset: str) -> frozenset[str]:
        body = await self._get_json(f"/lineage/{dataset}/impact")
        return frozenset(cast(list[str], body["impacted"]))

    async def catalog_show(self, dataset: str) -> DatasetOwner | None:
        response = await self._control_plane.get(f"/catalog/{dataset}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = cast(JsonObject, response.json())
        return DatasetOwner(
            dataset=cast(str, body["dataset"]),
            team=cast(str, body["team"]),
            owner=cast(str, body["owner"]),
        )

    async def run_show(self, run_id: UUID) -> RunView | None:
        response = await self._control_plane.get(f"/runs/{run_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = cast(JsonObject, response.json())
        steps = cast(list[JsonObject], body["steps"])
        return RunView(
            run_id=UUID(cast(str, body["id"])),
            status=cast(str, body["status"]),
            failed_steps=tuple(
                cast(str, step["name"]) for step in steps if step["status"] == "failed"
            ),
        )

    async def spec_head(self, pipeline_id: UUID) -> UUID | None:
        response = await self._control_plane.get(f"/pipelines/{pipeline_id}/specs/head")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = cast(JsonObject, response.json())
        return UUID(cast(str, body["version_id"]))

    async def _get_json(self, path: str) -> JsonObject:
        response = await self._control_plane.get(path)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.json().get("detail", response.text)
            raise LookupError(detail) from exc
        return cast(JsonObject, response.json())
