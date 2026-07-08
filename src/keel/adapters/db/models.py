from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    UniqueConstraint,
    DateTime,
    Identity,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from keel.domain.run import RunStatus


class Base(DeclarativeBase): ...


class RunRecord(Base):
    __tablename__ = "runs"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipelines.id"))
    status: Mapped[RunStatus] = mapped_column(SAEnum(RunStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    steps: Mapped[list["RunStepRecord"]] = relationship(
        order_by="RunStepRecord.sequence", cascade="all, delete-orphan"
    )


class RunStepRecord(Base):
    __tablename__ = "run_steps"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"))
    name: Mapped[str]
    status: Mapped[RunStatus] = mapped_column(SAEnum(RunStatus))
    sequence: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TeamRecord(Base):
    __tablename__ = "teams"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("name", name="uq_name"),)


class PipelineRecord(Base):
    __tablename__ = "pipelines"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_team_pipelinename"),)


class SpecVersionRecord(Base):
    __tablename__ = "spec_versions"

    version_id: Mapped[UUID] = mapped_column(primary_key=True)
    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipelines.id"))
    spec_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("spec_versions.version_id"))
    content: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_spec_versions_pipeline_seq", "pipeline_id", "seq"),
        UniqueConstraint(
            "pipeline_id",
            "parent_id",
            name="uq_spec_versions_pipeline_parent",
        ),
    )
