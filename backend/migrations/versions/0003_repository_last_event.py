"""track when each repository last delivered a webhook

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("last_event_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("repositories", "last_event_at")
