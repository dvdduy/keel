from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

_ERROR_MESSAGE_PREFIX = "Value error, "

type LocPart = str | int
type Loc = tuple[LocPart, ...]


@dataclass(frozen=True)
class Diagnostic:
    loc: str
    message: str


class SpecError(ValueError):
    """Base for every spec-boundary failure. Callers catch this, never pydantic."""


class SpecValidationError(SpecError):
    diagnostics: tuple[Diagnostic, ...]

    def __init__(self, diagnostics: Sequence[Diagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        super().__init__(str(self))

    def __str__(self) -> str:
        count = len(self.diagnostics)
        noun = "diagnostic" if count == 1 else "diagnostics"

        lines = [f"pipeline spec failed validation with {count} {noun}:"]
        lines.extend(f"- {diagnostic.loc}: {diagnostic.message}" for diagnostic in self.diagnostics)

        return "\n".join(lines)


def diagnostics_from_validation_error(error: ValidationError) -> tuple[Diagnostic, ...]:
    diagnostics = [
        Diagnostic(
            loc=_render_loc(_normalize_loc(error_detail.get("loc", ()))),
            message=_message_for_error(error_detail),
        )
        for error_detail in error.errors()
    ]

    return tuple(sorted(diagnostics, key=lambda diagnostic: (diagnostic.loc, diagnostic.message)))


def _normalize_loc(raw_loc: object) -> Loc:
    if isinstance(raw_loc, tuple):
        raw_parts = raw_loc
    elif isinstance(raw_loc, list):
        raw_parts = tuple(raw_loc)
    else:
        return ()

    loc_parts: list[LocPart] = []
    for part in raw_parts:
        if isinstance(part, str) or isinstance(part, int):
            loc_parts.append(part)
        else:
            loc_parts.append(str(part))

    return tuple(loc_parts)


def _render_loc(loc: Loc) -> str:
    path = ""

    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
            continue

        if path:
            path += f".{part}"
        else:
            path = part

    return path or "(root)"


def _message_for_error(error_detail: Mapping[str, Any]) -> str:
    error_type = str(error_detail.get("type", ""))
    raw_message = str(error_detail.get("msg", "invalid value"))
    context = error_detail.get("ctx", {})
    input_value = error_detail.get("input")

    if not isinstance(context, Mapping):
        context = {}

    if error_type == "value_error":
        return _strip_value_error_prefix(raw_message)

    if error_type == "greater_than":
        gt = context.get("gt")
        if gt is not None:
            return f"must be greater than {gt}"
        return "must be greater than the allowed minimum"

    if error_type == "missing":
        return "is required"

    if error_type == "extra_forbidden":
        return "is not a supported field"

    if error_type in {"enum", "literal_error"}:
        if input_value is not None:
            return f"has unsupported value {input_value!r}"
        return "has an unsupported value"

    if error_type in {"string_too_short", "too_short", "list_too_short", "tuple_too_short"}:
        return "must not be empty"

    if error_type in {"int_type", "int_parsing"}:
        return "must be an integer"

    if error_type == "string_type":
        return "must be a string"

    return _strip_value_error_prefix(raw_message)


def _strip_value_error_prefix(message: str) -> str:
    if message.startswith(_ERROR_MESSAGE_PREFIX):
        return message.removeprefix(_ERROR_MESSAGE_PREFIX)

    return message
