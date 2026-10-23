from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from rq import Queue
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.deps import get_queue
from app.models import PullRequest, Repository, ReviewRun, RunStatus
from app.schemas import PullRequestOut, RepositoryCreate, RepositoryOut, RunDetail
from app.security import Admin, CurrentUser, Reviewer
from app.services.queueing import enqueue_review

router = APIRouter(tags=["repositories"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/repos", response_model=list[RepositoryOut])
def list_repos(_: CurrentUser, db: DB) -> list[Repository]:
    return list(db.scalars(select(Repository).order_by(Repository.full_name)))


@router.post("/repos", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
def add_repo(body: RepositoryCreate, _: Admin, db: DB) -> Repository:
    repo = Repository(full_name=body.full_name)
    db.add(repo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Repository already registered") from None
    return repo


@router.get("/repos/{repo_id}/pulls", response_model=list[PullRequestOut])
def list_pulls(repo_id: int, _: CurrentUser, db: DB) -> list[PullRequest]:
    return list(
        db.scalars(
            select(PullRequest)
            .where(PullRequest.repository_id == repo_id)
            .options(selectinload(PullRequest.runs), joinedload(PullRequest.repository))
            .order_by(PullRequest.updated_at.desc())
        )
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, _: CurrentUser, db: DB) -> ReviewRun:
    run = db.get(
        ReviewRun,
        run_id,
        options=[
            selectinload(ReviewRun.findings),
            joinedload(ReviewRun.pull_request).joinedload(PullRequest.repository),
        ],
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@router.post("/runs/{run_id}/rerun", response_model=RunDetail, status_code=202)
def rerun(run_id: int, _: Reviewer, db: DB, queue: Annotated[Queue, Depends(get_queue)]) -> ReviewRun:
    run = db.get(ReviewRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run.status in (RunStatus.queued, RunStatus.running):
        raise HTTPException(status.HTTP_409_CONFLICT, "Run is already in progress")
    run.findings.clear()
    run.status = RunStatus.queued
    run.notes = run.error = run.started_at = run.finished_at = None
    db.commit()
    enqueue_review(db, queue, run)
    return run
