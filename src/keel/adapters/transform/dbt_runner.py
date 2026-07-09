from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence, cast

from keel.application.ports.transform import (
    ModelResult,
    ModelStatus,
    TransformError,
    TransformResult,
)


@dataclass(frozen=True)
class DbtTransformRunner:
    project_dir: Path
    warehouse_path: str
    executable: str = "dbt"

    def run(self, select: str) -> TransformResult:
        artifact_path = self.project_dir / "target" / "run_results.json"
        _remove_stale_artifact(artifact_path)

        env = os.environ.copy()
        env["KEEL_WAREHOUSE_PATH"] = self.warehouse_path

        command = [
            self.executable,
            "run",
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
            raise TransformError("transform tool failed to start") from exc

        return _read_run_results(
            artifact_path=artifact_path,
            returncode=completed.returncode,
            stderr=completed.stderr,
        )


def _remove_stale_artifact(artifact_path: Path) -> None:
    try:
        artifact_path.unlink()
    except FileNotFoundError:
        pass


def _read_run_results(
    *,
    artifact_path: Path,
    returncode: int,
    stderr: str,
) -> TransformResult:
    if not artifact_path.exists():
        detail = _tail(stderr)
        raise TransformError(
            "transform tool produced no interpretable run_results.json "
            f"(exit_code={returncode}){detail}"
        )

    try:
        raw_artifact: object = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransformError("transform tool produced unreadable run_results.json") from exc

    artifact = _as_mapping(raw_artifact, "run_results.json")
    raw_results = artifact.get("results")
    if not isinstance(raw_results, list):
        raise TransformError("run_results.json is missing a results list")

    models = tuple(_to_model_result(item) for item in cast(Sequence[object], raw_results))
    return TransformResult(
        ok=all(model.status == ModelStatus.SUCCESS for model in models),
        models=models,
    )


def _to_model_result(raw: object) -> ModelResult:
    item = _as_mapping(raw, "run_results.json result")

    unique_id = _required_string(item, "unique_id")
    status_value = _required_string(item, "status")

    try:
        status = ModelStatus(status_value)
    except ValueError as exc:
        raise TransformError(f"unsupported transform model status: {status_value!r}") from exc

    raw_message = item.get("message")
    message = raw_message if isinstance(raw_message, str) and raw_message else None

    return ModelResult(
        model=unique_id.rsplit(".", maxsplit=1)[-1],
        status=status,
        message=message,
    )


def _as_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TransformError(f"{context} is not an object")
    return cast(Mapping[str, object], value)


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise TransformError(f"run_results.json result is missing string field {key!r}")
    return value


def _tail(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    return f": {stripped[-500:]}"
