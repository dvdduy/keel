"""datasets catalog

Revision ID: c84e2f941a20
Revises: b3a9f0d8c2e1
Create Date: 2026-07-09 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c84e2f941a20"
down_revision: Union[str, Sequence[str], None] = "b3a9f0d8c2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("dataset", sa.String(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_name", sa.String(), nullable=False),
        sa.Column("team", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_spec_id", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"]),
        sa.PrimaryKeyConstraint("dataset"),
    )


def downgrade() -> None:
    op.drop_table("datasets")
