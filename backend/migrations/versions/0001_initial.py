"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=20)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(100), nullable=False),
        sa.Column("role", _enum("user_role", "viewer", "reviewer", "admin"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("html_url", sa.String(500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
    )
    op.create_table(
        "review_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("status", _enum("run_status", "queued", "running", "completed", "failed"), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("pull_request_id", "head_sha", name="uq_run_pr_sha"),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("tool", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.String(50), nullable=False),
        sa.Column(
            "severity",
            _enum("finding_severity", "low", "medium", "high", "critical"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_findings_run_id", "findings", ["run_id"])
    op.create_index("ix_findings_severity_created", "findings", ["severity", "created_at"])


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("review_runs")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    op.drop_table("users")
