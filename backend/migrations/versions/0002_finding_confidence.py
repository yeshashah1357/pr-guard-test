"""record analyzer confidence on findings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows and tools that don't report confidence (Ruff, LLM) stay NULL.
    op.add_column("findings", sa.Column("confidence", sa.String(10)))


def downgrade() -> None:
    op.drop_column("findings", "confidence")
