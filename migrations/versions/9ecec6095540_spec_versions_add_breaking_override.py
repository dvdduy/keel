"""spec_versions add breaking_override

Revision ID: 9ecec6095540
Revises: d5b07061b01e
Create Date: 2026-07-08 11:29:25.513296

"""

from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9ecec6095540"
down_revision: Union[str, Sequence[str], None] = "d5b07061b01e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spec_versions",
        sa.Column(
            "breaking_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("spec_versions", "breaking_override")
