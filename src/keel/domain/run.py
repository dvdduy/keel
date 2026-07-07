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


@dataclass
class RunStep:
    id: UUID
    run_id: UUID
    name: str
    status: RunStatus
    sequence: int
    created_at: datetime


@dataclass
class Run:
    id: UUID
    pipeline_id: UUID
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[RunStep] = field(default_factory=list)


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
