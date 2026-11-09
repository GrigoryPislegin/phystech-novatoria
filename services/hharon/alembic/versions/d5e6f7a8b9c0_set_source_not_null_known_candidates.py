# pyright: reportUnusedCallResult=false
"""set source NOT NULL on known_candidates

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-02-20

Run this migration AFTER the datafix has backfilled source for existing rows.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Set source column to NOT NULL."""
    op.alter_column(
        "known_candidates",
        "source",
        existing_type=sa.String(50),
        nullable=False,
    )


def downgrade() -> None:
    """Set source column back to nullable."""
    op.alter_column(
        "known_candidates",
        "source",
        existing_type=sa.String(50),
        nullable=True,
    )
