from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATASET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceType(StrEnum):
    CSV = "csv"


class ColumnType(StrEnum):
    INTEGER = "integer"
    DECIMAL = "decimal"
    TIMESTAMP = "timestamp"
    STRING = "string"
    BOOLEAN = "boolean"


class QualityCheckType(StrEnum):
    NOT_NULL = "not_null"
    UNIQUE = "unique"


class SourceSpec(StrictModel):
    type: SourceType
    path: str

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("source.path must not be blank")
        return value


class ContractColumn(StrictModel):
    name: str
    type: ColumnType
    nullable: bool = True

    @field_validator("name")
    @classmethod
    def name_must_be_identifier(cls, value: str) -> str:
        value = value.strip()
        if not _IDENTIFIER_RE.match(value):
            raise ValueError(
                "contract column name must be a valid identifier, " "for example: order_id"
            )
        return value


class FreshnessSpec(StrictModel):
    max_age_minutes: int = Field(gt=0)


class QualityCheckSpec(StrictModel):
    type: QualityCheckType
    column: str

    @field_validator("column")
    @classmethod
    def column_must_be_identifier(cls, value: str) -> str:
        value = value.strip()
        if not _IDENTIFIER_RE.match(value):
            raise ValueError(
                "quality check column must be a valid identifier, " "for example: order_id"
            )
        return value


class PipelineSpec(StrictModel):
    name: str
    team: str
    owner: str
    source: SourceSpec
    destination: str
    contract: tuple[ContractColumn, ...]
    transform: str | None = None
    freshness: FreshnessSpec
    quality_checks: tuple[QualityCheckSpec, ...] = ()

    @field_validator("name", "team")
    @classmethod
    def value_must_be_identifier(cls, value: str) -> str:
        value = value.strip()
        if not _IDENTIFIER_RE.match(value):
            raise ValueError("value must be a valid identifier")

        return value

    @field_validator("owner")
    @classmethod
    def owner_must_look_like_email(cls, value: str) -> str:
        value = value.strip()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("owner must be an email-like value")

        return value

    @field_validator("destination")
    @classmethod
    def destination_must_be_schema_dot_table(cls, value: str) -> str:
        value = value.strip()
        if not _DATASET_RE.match(value):
            raise ValueError("destination must use schema.table format, " "for example: raw.orders")
        return value

    @field_validator("transform")
    @classmethod
    def transform_must_be_identifier_or_none(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        if not _IDENTIFIER_RE.match(value):
            raise ValueError(
                "transform must be a valid model reference, " "for example: stg_orders"
            )
        return value

    @model_validator(mode="after")
    def validate_contract_references(self) -> Self:
        contract_column_names = [column.name for column in self.contract]
        unique_column_names = set(contract_column_names)

        if len(contract_column_names) != len(unique_column_names):
            raise ValueError("contract column names must be unique")

        for check in self.quality_checks:
            if check.column not in unique_column_names:
                raise ValueError(f"quality check references unknown column: {check.column}")

        seen_quality_checks: set[tuple[QualityCheckType, str]] = set()

        for index, check in enumerate(self.quality_checks):
            identity = (check.type, check.column)

            if identity in seen_quality_checks:
                raise ValueError(
                    f"quality_checks[{index}]: duplicate check "
                    f"{check.type.value} on {check.column}"
                )

            seen_quality_checks.add(identity)

        return self
