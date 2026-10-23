from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Finding, PullRequest, Repository, ReviewRun, Severity
from app.schemas import FindingOut, FindingPage, FindingRow, TrendPoint
from app.security import CurrentUser

router = APIRouter(tags=["findings"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/findings", response_model=FindingPage)
def list_findings(
    _: CurrentUser,
    db: DB,
    repo_id: int | None = None,
    run_id: int | None = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
    tool: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FindingPage:
    base = (
        select(Finding, Repository.full_name, PullRequest.number, PullRequest.html_url)
        .join(ReviewRun, Finding.run_id == ReviewRun.id)
        .join(PullRequest, ReviewRun.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
    )
    if repo_id is not None:
        base = base.where(Repository.id == repo_id)
    if run_id is not None:
        base = base.where(Finding.run_id == run_id)
    if severity:
        base = base.where(Finding.severity.in_(severity))
    if tool:
        base = base.where(Finding.tool == tool)

    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Finding.created_at.desc(), Finding.id.desc()).limit(limit).offset(offset))
    items = [
        FindingRow(
            **FindingOut.model_validate(f).model_dump(),
            repository=full_name,
            pr_number=number,
            pr_url=url,
        )
        for f, full_name, number, url in rows
    ]
    return FindingPage(items=items, total=total or 0)


@router.get("/stats/trends", response_model=list[TrendPoint])
def trends(
    _: CurrentUser,
    db: DB,
    repo_id: int | None = None,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[TrendPoint]:
    """Findings per day per severity — one GROUP BY, so the chart costs one query."""
    since = datetime.now(UTC) - timedelta(days=days)
    day = func.date(Finding.created_at)
    query = (
        select(day.label("day"), Finding.severity, func.count().label("count"))
        .where(Finding.created_at >= since)
        .group_by(day, Finding.severity)
        .order_by(day)
    )
    if repo_id is not None:
        query = (
            query.join(ReviewRun, Finding.run_id == ReviewRun.id)
            .join(PullRequest, ReviewRun.pull_request_id == PullRequest.id)
            .where(PullRequest.repository_id == repo_id)
        )
    # Postgres returns a date; SQLite (used in tests) returns 'YYYY-MM-DD'. Pydantic parses both.
    return [TrendPoint(day=d, severity=s, count=c) for d, s, c in db.execute(query)]
