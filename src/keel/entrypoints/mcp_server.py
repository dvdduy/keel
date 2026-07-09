from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast
from uuid import UUID

import httpx
from mcp.server.fastmcp import FastMCP

from keel.adapters.control_plane.read_only_client import ReadOnlyControlPlane
from keel.entrypoints.cli import get_base_url


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class ClientFactory(Protocol):
    def __call__(self, base_url: str) -> httpx.AsyncClient: ...


def _default_client_factory(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=10.0)


def _json_body(response: httpx.Response) -> JsonValue:
    return cast(JsonValue, response.json())


async def _read_json(response: httpx.Response) -> JsonValue:
    body = _json_body(response)
    if response.status_code < 400:
        return body

    detail = body.get("detail") if isinstance(body, dict) else body
    return {"status": response.status_code, "error": detail}


async def catalog_list(cp: ReadOnlyControlPlane) -> JsonValue:
    response = await cp.get("/catalog")
    return await _read_json(response)


async def catalog_show(cp: ReadOnlyControlPlane, dataset: str) -> JsonValue:
    response = await cp.get(f"/catalog/{dataset}")
    return await _read_json(response)


async def run_show(cp: ReadOnlyControlPlane, run_id: UUID) -> JsonValue:
    response = await cp.get(f"/runs/{run_id}")
    return await _read_json(response)


async def lineage_impact(cp: ReadOnlyControlPlane, dataset: str) -> JsonValue:
    response = await cp.get(f"/lineage/{dataset}/impact")
    return await _read_json(response)


async def spec_head(cp: ReadOnlyControlPlane, pipeline_id: UUID) -> JsonValue:
    response = await cp.get(f"/pipelines/{pipeline_id}/specs/head")
    return await _read_json(response)


def build_mcp_server(
    *,
    client_factory: ClientFactory = _default_client_factory,
    environ: Mapping[str, str] | None = None,
) -> FastMCP:
    server = FastMCP("Keel")

    async def call_tool(
        tool: Callable[[ReadOnlyControlPlane], Awaitable[JsonValue]],
    ) -> JsonValue:
        base_url = get_base_url(environ)
        async with client_factory(base_url) as client:
            return await tool(ReadOnlyControlPlane(client))

    @server.tool(name="catalog_list")
    async def catalog_list_tool() -> JsonValue:
        return await call_tool(catalog_list)

    @server.tool(name="catalog_show")
    async def catalog_show_tool(dataset: str) -> JsonValue:
        return await call_tool(lambda cp: catalog_show(cp, dataset))

    @server.tool(name="run_show")
    async def run_show_tool(run_id: UUID) -> JsonValue:
        return await call_tool(lambda cp: run_show(cp, run_id))

    @server.tool(name="lineage_impact")
    async def lineage_impact_tool(dataset: str) -> JsonValue:
        return await call_tool(lambda cp: lineage_impact(cp, dataset))

    @server.tool(name="spec_head")
    async def spec_head_tool(pipeline_id: UUID) -> JsonValue:
        return await call_tool(lambda cp: spec_head(cp, pipeline_id))

    return server


def main() -> None:
    build_mcp_server().run()


if __name__ == "__main__":
    main()
