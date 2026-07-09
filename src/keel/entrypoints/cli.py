from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import httpx

DEFAULT_API_URL = "http://localhost:8000"


class ClientFactory(Protocol):
    def __call__(self, base_url: str) -> httpx.AsyncClient: ...


def get_base_url(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return source.get("KEEL_API_URL", DEFAULT_API_URL)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keel")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    spec = subparsers.add_parser("spec")
    spec_commands = spec.add_subparsers(dest="command", required=True)

    submit = spec_commands.add_parser("submit")
    submit.add_argument("pipeline_id")
    submit.add_argument("path")
    submit.add_argument("--allow-breaking", action="store_true")
    submit.add_argument("--json", action="store_true", dest="as_json")

    head = spec_commands.add_parser("head")
    head.add_argument("pipeline_id")
    head.add_argument("--json", action="store_true", dest="as_json")

    catalog = subparsers.add_parser("catalog")
    catalog_commands = catalog.add_subparsers(dest="command", required=True)

    catalog_list = catalog_commands.add_parser("list")
    catalog_list.add_argument("--json", action="store_true", dest="as_json")

    catalog_show = catalog_commands.add_parser("show")
    catalog_show.add_argument("dataset")
    catalog_show.add_argument("--json", action="store_true", dest="as_json")

    run = subparsers.add_parser("run")
    run_commands = run.add_subparsers(dest="command", required=True)

    run_show = run_commands.add_parser("show")
    run_show.add_argument("run_id")
    run_show.add_argument("--json", action="store_true", dest="as_json")

    lineage = subparsers.add_parser("lineage")
    lineage_commands = lineage.add_subparsers(dest="command", required=True)

    impact = lineage_commands.add_parser("impact")
    impact.add_argument("dataset")
    impact.add_argument("--json", action="store_true", dest="as_json")

    return parser


def _default_client_factory(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=10.0)


async def _request(args: argparse.Namespace, client: httpx.AsyncClient) -> httpx.Response:
    resource = str(args.resource)
    command = str(args.command)

    if resource == "spec" and command == "submit":
        spec_yaml = Path(str(args.path)).read_text()
        return await client.post(
            f"/pipelines/{args.pipeline_id}/specs",
            params={"allow_breaking": bool(args.allow_breaking)},
            content=spec_yaml,
            headers={"content-type": "application/x-yaml"},
        )
    if resource == "spec" and command == "head":
        return await client.get(f"/pipelines/{args.pipeline_id}/specs/head")
    if resource == "catalog" and command == "list":
        return await client.get("/catalog")
    if resource == "catalog" and command == "show":
        return await client.get(f"/catalog/{args.dataset}")
    if resource == "run" and command == "show":
        return await client.get(f"/runs/{args.run_id}")
    if resource == "lineage" and command == "impact":
        return await client.get(f"/lineage/{args.dataset}/impact")

    raise AssertionError(f"unhandled command: {resource} {command}")


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"detail": response.text}


def _print_json(value: Any) -> None:
    print(json.dumps(value, sort_keys=True))


def _format_success(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "No results."
        return "\n".join(_format_success(item) for item in value)

    if not isinstance(value, dict):
        return str(value)

    if "version_id" in value:
        return (
            f"Spec {value['spec_id']} accepted for pipeline {value['pipeline_id']}\n"
            f"version: {value['version_id']}\n"
            f"parent: {value['parent_id'] or '(none)'}\n"
            f"breaking override: {value['breaking_override']}"
        )
    if "columns" in value and "dataset" in value:
        columns = ", ".join(column["name"] for column in value["columns"])
        return (
            f"{value['dataset']}\n"
            f"pipeline: {value['pipeline_name']}\n"
            f"owner: {value['owner']}\n"
            f"columns: {columns or '(none)'}"
        )
    if "steps" in value and "status" in value:
        return (
            f"Run {value['id']}\n"
            f"pipeline: {value['pipeline_id']}\n"
            f"status: {value['status']}\n"
            f"watermark: {value['watermark'] or '(none)'}"
        )
    if "impacted" in value and "dataset" in value:
        impacted = ", ".join(value["impacted"]) or "(none)"
        return f"Impact for {value['dataset']}\nimpacted: {impacted}"

    return json.dumps(value, indent=2, sort_keys=True)


def _format_error(response: httpx.Response) -> str:
    body = _json_body(response)
    detail = body.get("detail") if isinstance(body, dict) else None

    if response.status_code == 409 and isinstance(detail, dict):
        changes = detail.get("breaking_changes", [])
        lines = ["Breaking spec change rejected:"]
        for change in changes:
            if isinstance(change, dict):
                lines.append(
                    f"- {change.get('column', '(unknown)')}: "
                    f"{change.get('detail', 'breaking change')} "
                    f"({change.get('kind', 'unknown')})"
                )
        if len(lines) == 1:
            lines.append(f"- {detail.get('message', 'breaking change')}")
        lines.append("Re-run with --allow-breaking only when this change is intentional.")
        return "\n".join(lines)

    if response.status_code == 422 and isinstance(detail, dict):
        diagnostics = detail.get("diagnostics")
        if isinstance(diagnostics, list):
            lines = ["Spec diagnostics:"]
            for diagnostic in diagnostics:
                if isinstance(diagnostic, dict):
                    lines.append(
                        f"- {diagnostic.get('loc', '(unknown)')}: "
                        f"{diagnostic.get('message', 'invalid value')}"
                    )
            return "\n".join(lines)
        message = detail.get("message")
        if isinstance(message, str):
            return f"Spec rejected: {message}"

    if response.status_code == 404:
        message = detail if isinstance(detail, str) else "resource not found"
        return f"Not found: {message}"

    message = detail if isinstance(detail, str) else response.text
    return f"Request failed with HTTP {response.status_code}: {message}"


async def _run(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = _default_client_factory,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    base_url = get_base_url(environ)

    try:
        async with client_factory(base_url) as client:
            response = await _request(args, client)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError):
        print(f"Keel control plane is not reachable at {base_url}.")
        return 1
    except OSError as exc:
        print(f"Could not read input: {exc}")
        return 1

    body = _json_body(response)
    if response.is_success:
        if bool(args.as_json):
            _print_json(body)
        else:
            print(_format_success(body))
        return 0

    if bool(args.as_json):
        _print_json(body)
    else:
        print(_format_error(response))
    return 1


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = _default_client_factory,
    environ: Mapping[str, str] | None = None,
) -> int:
    return asyncio.run(_run(argv, client_factory=client_factory, environ=environ))


if __name__ == "__main__":
    sys.exit(main())
