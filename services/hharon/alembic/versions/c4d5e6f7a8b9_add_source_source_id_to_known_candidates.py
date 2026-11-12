# pyright: reportUnusedCallResult=false
"""add source and source_id to known_candidates (nullable)

Revision ID: c4d5e6f7a8b9
Revises: 8581599ceb79
Create Date: 2026-02-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "8581599ceb79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source and source_id columns as nullable."""
    op.add_column("known_candidates", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("known_candidates", sa.Column("source_id", sa.UUID(), nullable=True))


def downgrade() -> None:
    """Remove source and source_id columns."""
    op.drop_column("known_candidates", "source_id")
    op.drop_column("known_candidates", "source")
