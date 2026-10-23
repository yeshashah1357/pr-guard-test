import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(enum.StrEnum):
    viewer = "viewer"
    reviewer = "reviewer"
    admin = "admin"


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class Severity(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


SEVERITY_RANK = {Severity.low: 0, Severity.medium: 1, Severity.high: 2, Severity.critical: 3}


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # Stored as VARCHAR + CHECK so adding a value never needs an ALTER TYPE.
    return Enum(cls, name=name, native_enum=False, length=20, validate_strings=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.viewer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(100))
    head_sha: Mapped[str] = mapped_column(String(40))
    html_url: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")
    runs: Mapped[list["ReviewRun"]] = relationship(
        back_populates="pull_request", order_by="ReviewRun.id.desc()"
    )

    @property
    def latest_run(self) -> "ReviewRun | None":
        return self.runs[0] if self.runs else None

    @property
    def repository_name(self) -> str:
        return self.repository.full_name


class ReviewRun(Base):
    __tablename__ = "review_runs"
    # One run per commit: GitHub redelivers webhooks, and this makes that a no-op.
    __table_args__ = (UniqueConstraint("pull_request_id", "head_sha", name="uq_run_pr_sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"))
    head_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), default=RunStatus.queued)
    notes: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pull_request: Mapped[PullRequest] = relationship(back_populates="runs")
    findings: Mapped[list["Finding"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_run_id", "run_id"),
        # Serves the dashboard's "filter by severity, newest first" and the trend query.
        Index("ix_findings_severity_created", "severity", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("review_runs.id", ondelete="CASCADE"))
    tool: Mapped[str] = mapped_column(String(20))
    rule_id: Mapped[str] = mapped_column(String(50))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "finding_severity"))
    file_path: Mapped[str] = mapped_column(String(500))
    line: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ReviewRun] = relationship(back_populates="findings")
