from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence, cast

from keel.application.ports.transform import (
    ManifestNode,
    ModelResult,
    ModelStatus,
    TestReport,
    TestResult,
    TestStatus,
    TransformError,
    TransformManifest,
    TransformResult,
)


@dataclass(frozen=True)
class DbtTransformRunner:
    project_dir: Path
    warehouse_path: str
    executable: str = "dbt"

    def run(self, select: str) -> TransformResult:
        raw_results = self._invoke_and_load_run_results("run", select)
        models = tuple(_to_model_result(item) for item in raw_results)
        return TransformResult(
            ok=all(model.status == ModelStatus.SUCCESS for model in models),
            models=models,
        )

    def test(self, select: str) -> TestReport:
        raw_results = self._invoke_and_load_run_results("test", select)
        tests = tuple(_to_test_result(item) for item in raw_results)
        return TestReport(
            ok=all(_is_non_blocking_test_status(test.status) for test in tests),
            tests=tests,
        )

    def capture_manifest(self) -> TransformManifest:
        artifact_path = self.project_dir / "target" / "manifest.json"
        if not artifact_path.exists():
            raise TransformError("transform tool produced no manifest.json to capture")

        artifact = _read_json_artifact(artifact_path, "manifest.json")
        raw_nodes = _required_object_map(artifact, "nodes", "manifest.json")
        raw_sources = _required_object_map(artifact, "sources", "manifest.json")

        nodes: list[ManifestNode] = []
        for raw_collection in (raw_nodes, raw_sources):
            for unique_id, raw_node in raw_collection.items():
                nodes.append(_to_manifest_node(unique_id, raw_node))

        return TransformManifest(nodes=tuple(nodes))

    def _invoke_and_load_run_results(
        self,
        command_name: str,
        select: str,
    ) -> tuple[Mapping[str, object], ...]:
        artifact_path = self.project_dir / "target" / "run_results.json"
        _remove_stale_artifact(artifact_path)

        env = os.environ.copy()
        env["KEEL_WAREHOUSE_PATH"] = self.warehouse_path

        command = [
            self.executable,
            command_name,
            "--select",
            select,
            "--project-dir",
            str(self.project_dir),
            "--profiles-dir",
            str(self.project_dir),
        ]

        try:
            completed = subprocess.run(
                command,
                cwd=self.project_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise TransformError(
                f"transform tool failed to start: {self.executable!r} ({exc})"
            ) from exc

        return _load_run_results(
            artifact_path=artifact_path,
            returncode=completed.returncode,
            stderr=completed.stderr,
        )


def _remove_stale_artifact(artifact_path: Path) -> None:
    try:
        artifact_path.unlink()
    except FileNotFoundError:
        pass


def _load_run_results(
    *,
    artifact_path: Path,
    returncode: int,
    stderr: str,
) -> tuple[Mapping[str, object], ...]:
    if not artifact_path.exists():
        detail = _tail(stderr)
        raise TransformError(
            "transform tool produced no interpretable run_results.json "
            f"(exit_code={returncode}){detail}"
        )

    artifact = _read_json_artifact(artifact_path, "run_results.json")
    raw_results = artifact.get("results")
    if not isinstance(raw_results, list):
        raise TransformError("run_results.json is missing a results list")

    return tuple(
        _as_mapping(item, "run_results.json result") for item in cast(Sequence[object], raw_results)
    )


def _read_json_artifact(artifact_path: Path, artifact_name: str) -> Mapping[str, object]:
    try:
        raw_artifact: object = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransformError(f"transform tool produced unreadable {artifact_name}") from exc

    return _as_mapping(raw_artifact, artifact_name)


def _to_model_result(item: Mapping[str, object]) -> ModelResult:
    unique_id = _required_string(item, "unique_id", "run_results.json result")
    status_value = _required_string(item, "status", "run_results.json result")

    try:
        status = ModelStatus(status_value)
    except ValueError as exc:
        raise TransformError(f"unsupported transform model status: {status_value!r}") from exc

    return ModelResult(
        model=unique_id.rsplit(".", maxsplit=1)[-1],
        status=status,
        message=_optional_string(item, "message"),
    )


def _to_test_result(item: Mapping[str, object]) -> TestResult:
    unique_id = _required_string(item, "unique_id", "run_results.json result")
    status_value = _required_string(item, "status", "run_results.json result")

    try:
        status = TestStatus(status_value)
    except ValueError as exc:
        raise TransformError(f"unsupported transform test status: {status_value!r}") from exc

    return TestResult(
        test=_short_test_name(unique_id),
        status=status,
        failures=_failures(item),
        message=_optional_string(item, "message"),
    )


def _is_non_blocking_test_status(status: TestStatus) -> bool:
    # dbt severity:warn is intentionally non-blocking by default. Day 18's
    # Keel quality gates will provide the stricter quarantine surface.
    return status in {TestStatus.PASS, TestStatus.SKIPPED, TestStatus.WARN}


def _failures(item: Mapping[str, object]) -> int:
    value = item.get("failures")
    if value is None:
        return 0

    if isinstance(value, bool) or not isinstance(value, int):
        raise TransformError("run_results.json test result has non-integer failures")

    return value


def _to_manifest_node(unique_id: str, raw_node: object) -> ManifestNode:
    item = _as_mapping(raw_node, "manifest.json node")
    return ManifestNode(
        unique_id=unique_id,
        resource_type=_required_string(item, "resource_type", "manifest.json node"),
        name=_required_string(item, "name", "manifest.json node"),
        schema=_required_string(item, "schema", "manifest.json node"),
        relation=_relation_name(item),
        depends_on=_depends_on_nodes(item.get("depends_on")),
    )


def _relation_name(item: Mapping[str, object]) -> str:
    resource_type = _required_string(item, "resource_type", "manifest.json node")

    if resource_type == "source":
        identifier = _optional_string(item, "identifier")
        if identifier is not None:
            return identifier

        return _required_string(item, "name", "manifest.json node")

    alias = _optional_string(item, "alias")
    if alias is not None:
        return alias

    return _required_string(item, "name", "manifest.json node")


def _depends_on_nodes(raw_depends_on: object) -> frozenset[str]:
    if raw_depends_on is None:
        return frozenset()

    depends_on = _as_mapping(raw_depends_on, "manifest.json node depends_on")
    raw_nodes = depends_on.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise TransformError("manifest.json node depends_on.nodes is not a list")

    nodes: list[str] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, str) or not raw_node:
            raise TransformError("manifest.json node depends_on.nodes contains a non-string")
        nodes.append(raw_node)

    return frozenset(nodes)


def _required_object_map(
    mapping: Mapping[str, object],
    key: str,
    context: str,
) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise TransformError(f"{context} is missing object field {key!r}")
    return cast(Mapping[str, object], value)


def _as_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TransformError(f"{context} is not an object")
    return cast(Mapping[str, object], value)


def _required_string(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise TransformError(f"{context} is missing string field {key!r}")
    return value


def _optional_string(mapping: Mapping[str, object], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) and value else None


def _tail(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    return f": {stripped[-500:]}"


def _short_test_name(unique_id: str) -> str:
    parts = unique_id.split(".")

    # dbt generic tests commonly look like:
    # test.<project>.<generated_test_name>.<hash>
    # The final segment is only a stability hash, not the useful test name.
    if unique_id.startswith("test.") and len(parts) >= 4:
        return parts[-2]

    return parts[-1]
