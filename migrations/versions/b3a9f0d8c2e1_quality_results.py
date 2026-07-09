"""quality results

Revision ID: b3a9f0d8c2e1
Revises: 91ca261b21f5
Create Date: 2026-07-08 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3a9f0d8c2e1"
down_revision: Union[str, Sequence[str], None] = "91ca261b21f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "check_type",
            sa.Enum("NOT_NULL", "UNIQUE", name="qualitychecktype"),
            nullable=False,
        ),
        sa.Column("column", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PASSED", "FAILED", "UNKNOWN", name="checkstatus"),
            nullable=False,
        ),
        sa.Column("violations", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_results_run_id",
        "quality_results",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quality_results_run_id", table_name="quality_results")
    op.drop_table("quality_results")
    op.execute("DROP TYPE IF EXISTS checkstatus")
    op.execute("DROP TYPE IF EXISTS qualitychecktype")
