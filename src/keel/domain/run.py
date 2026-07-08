from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class IllegalStateTransition(Exception):
    """Raised when a Run or RunStep attempts an invalid lifecycle transition."""


@dataclass
class RunStep:
    id: UUID
    run_id: UUID
    name: str
    sequence: int
    created_at: datetime
    status: RunStatus = RunStatus.PENDING

    def start(self) -> None:
        self._transition(expected=RunStatus.PENDING, next_status=RunStatus.RUNNING, action="start")

    def succeed(self) -> None:
        self._transition(
            expected=RunStatus.RUNNING, next_status=RunStatus.SUCCESS, action="succeed"
        )

    def fail(self) -> None:
        self._transition(expected=RunStatus.RUNNING, next_status=RunStatus.FAILED, action="fail")

    def _transition(self, *, expected: RunStatus, next_status: RunStatus, action: str) -> None:
        if self.status != expected:
            raise IllegalStateTransition(
                f"cannot {action} run step {self.name!r} from {self.status.value}; "
                f"expected {expected.value}"
            )

        self.status = next_status


@dataclass
class Run:
    id: UUID
    pipeline_id: UUID
    created_at: datetime
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[RunStep] = field(default_factory=list)

    def start(self, now: datetime) -> None:
        self._transition(expected=RunStatus.PENDING, next_status=RunStatus.RUNNING, action="start")
        self.started_at = now

    def succeed(self, now: datetime) -> None:
        self._transition(
            expected=RunStatus.RUNNING, next_status=RunStatus.SUCCESS, action="succeed"
        )
        self.finished_at = now

    def fail(self, now: datetime) -> None:
        self._transition(expected=RunStatus.RUNNING, next_status=RunStatus.FAILED, action="fail")
        self.finished_at = now

    def _transition(self, *, expected: RunStatus, next_status: RunStatus, action: str) -> None:
        if self.status != expected:
            raise IllegalStateTransition(
                f"cannot {action} run {self.id} from {self.status.value}; "
                f"expected {expected.value}"
            )

        self.status = next_status

    def add_step(self, step: RunStep) -> None:
        self.steps.append(step)


@dataclass
class Team:
    id: UUID
    name: str
    created_at: datetime


@dataclass
class Pipeline:
    id: UUID
    name: str
    team_id: UUID
    created_at: datetime
    runs: list[Run] = field(default_factory=list)
