from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from keel.application.specs.models import ColumnType, PipelineSpec


class DriftKind(StrEnum):
    MISSING_TABLE = "missing_table"
    MISSING_COLUMN = "missing_column"
    UNEXPECTED_COLUMN = "unexpected_column"
    TYPE_MISMATCH = "type_mismatch"


@dataclass(frozen=True)
class ObservedColumn:
    name: str
    type: ColumnType


@dataclass(frozen=True)
class ObservedSchema:
    columns: tuple[ObservedColumn, ...]


@dataclass(frozen=True)
class SchemaDrift:
    kind: DriftKind
    column: str | None
    detail: str


@dataclass(frozen=True)
class DriftReport:
    table: str
    drifts: tuple[SchemaDrift, ...]

    @property
    def in_sync(self) -> bool:
        return not self.drifts


def detect_drift(spec: PipelineSpec, observed: ObservedSchema | None) -> DriftReport:
    """Diff declared contract against observed materialized schema."""

    if observed is None:
        return DriftReport(
            table=spec.destination,
            drifts=(
                SchemaDrift(
                    kind=DriftKind.MISSING_TABLE,
                    column=None,
                    detail=f"table {spec.destination} is missing",
                ),
            ),
        )

    observed_by_name = {column.name: column for column in observed.columns}
    declared_by_name = {column.name: column for column in spec.contract}

    drifts: list[SchemaDrift] = []

    for declared in spec.contract:
        actual = observed_by_name.get(declared.name)

        if actual is None:
            drifts.append(
                SchemaDrift(
                    kind=DriftKind.MISSING_COLUMN,
                    column=declared.name,
                    detail=(
                        f"declared column {declared.name} is missing from " f"{spec.destination}"
                    ),
                )
            )
            continue

        if actual.type != declared.type:
            drifts.append(
                SchemaDrift(
                    kind=DriftKind.TYPE_MISMATCH,
                    column=declared.name,
                    detail=(
                        f"declared column {declared.name} expected type "
                        f"{declared.type.value}, observed {actual.type.value}"
                    ),
                )
            )

    for actual in observed.columns:
        if actual.name not in declared_by_name:
            drifts.append(
                SchemaDrift(
                    kind=DriftKind.UNEXPECTED_COLUMN,
                    column=actual.name,
                    detail=(
                        f"observed column {actual.name} is not declared in " f"{spec.destination}"
                    ),
                )
            )

    return DriftReport(table=spec.destination, drifts=tuple(drifts))
