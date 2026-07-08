from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from keel.application.specs.diagnostics import SpecError
from keel.application.specs.models import ColumnType, PipelineSpec


class BreakingKind(StrEnum):
    COLUMN_DROPPED = "column_dropped"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_MADE_REQUIRED = "column_made_required"
    REQUIRED_COLUMN_ADDED = "required_column_added"


@dataclass(frozen=True)
class BreakingChange:
    kind: BreakingKind
    column: str
    detail: str


@dataclass(frozen=True)
class CompatibilityReport:
    breaking_changes: tuple[BreakingChange, ...]

    @property
    def compatible(self) -> bool:
        return not self.breaking_changes


class IncompatibleSpecError(SpecError):
    """Raised when a breaking spec change is rejected. Carries the diff."""

    report: CompatibilityReport

    def __init__(self, report: CompatibilityReport) -> None:
        self.report = report

        details = "; ".join(
            f"{change.column}: {change.detail}" for change in report.breaking_changes
        )

        message = (
            "Breaking spec change rejected"
            if not details
            else f"Breaking spec change rejected: {details}"
        )

        super().__init__(message)


_WIDENINGS: frozenset[tuple[ColumnType, ColumnType]] = frozenset(
    {(ColumnType.INTEGER, ColumnType.DECIMAL)}
)


def check_compatibility(previous: PipelineSpec, proposed: PipelineSpec) -> CompatibilityReport:
    """Classify the contract change from `previous` to `proposed`.

    Direction: can a consumer of `previous` still consume data produced under
    `proposed`? Equivalently, does `proposed` accept every dataset `previous`
    accepted, plus the no-column-removal rule?

    Compares ONLY `contract` columns, matched by name. Reports all breaking
    changes, no just the first.
    """
    previous_columns = {column.name: column for column in previous.contract}
    proposed_columns = {column.name: column for column in proposed.contract}

    breaking_changes: list[BreakingChange] = []

    for column_name, previous_column in previous_columns.items():
        proposed_column = proposed_columns.get(column_name)

        if proposed_column is None:
            breaking_changes.append(
                BreakingChange(
                    kind=BreakingKind.COLUMN_DROPPED,
                    column=column_name,
                    detail="column was removed from the contract",
                )
            )
            continue

        if (
            previous_column.type != proposed_column.type
            and (previous_column.type, proposed_column.type) not in _WIDENINGS
        ):
            breaking_changes.append(
                BreakingChange(
                    kind=BreakingKind.COLUMN_TYPE_CHANGED,
                    column=column_name,
                    detail=(
                        f"type {previous_column.type} -> {proposed_column.type} "
                        "is not a widening"
                    ),
                )
            )

        if previous_column.nullable and not proposed_column.nullable:
            breaking_changes.append(
                BreakingChange(
                    kind=BreakingKind.COLUMN_MADE_REQUIRED,
                    column=column_name,
                    detail="column changed from nullable to required",
                )
            )

    for column_name, proposed_column in proposed_columns.items():
        if column_name in previous_columns:
            continue

        if not proposed_column.nullable:
            breaking_changes.append(
                BreakingChange(
                    kind=BreakingKind.REQUIRED_COLUMN_ADDED,
                    column=column_name,
                    detail="new required column was added",
                )
            )

    return CompatibilityReport(breaking_changes=tuple(breaking_changes))
