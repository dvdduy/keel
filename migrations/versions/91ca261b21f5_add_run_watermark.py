"""add run watermark

Revision ID: 91ca261b21f5
Revises: 9ecec6095540
Create Date: 2026-07-08 15:20:08.872135

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "91ca261b21f5"
down_revision: Union[str, Sequence[str], None] = "9ecec6095540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "runs",
        sa.Column("watermark", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_runs_pipeline_id_watermark",
        "runs",
        ["pipeline_id", "watermark"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_runs_pipeline_id_watermark", table_name="runs")
    op.drop_column("runs", "watermark")
