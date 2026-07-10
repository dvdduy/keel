from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionEffect(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class AgentAction:
    name: str
    effect: ActionEffect


@dataclass(frozen=True)
class Approval:
    approver: str


class ApprovalRequired(Exception):
    pass


def authorize(action: AgentAction, approval: Approval | None) -> None:
    if action.effect == ActionEffect.WRITE and approval is None:
        raise ApprovalRequired(action.name)
