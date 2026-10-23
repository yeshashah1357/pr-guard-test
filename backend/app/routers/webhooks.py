import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_queue
from app.models import PullRequest, Repository, ReviewRun
from app.schemas import PullRequestEvent
from app.services.queueing import enqueue_review

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

REVIEW_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def _record_delivery(db: Session, body: bytes) -> None:
    try:
        full_name = json.loads(body)["repository"]["full_name"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return
    repo = db.scalar(select(Repository).where(Repository.full_name == full_name))
    if repo is not None:
        repo.last_event_at = datetime.now(UTC)
        db.commit()


async def raw_body(request: Request) -> bytes:
    # The signature covers the exact bytes GitHub sent, so we verify before parsing.
    return await request.body()


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
def github_webhook(
    body: Annotated[bytes, Depends(raw_body)],
    db: Annotated[Session, Depends(get_db)],
    queue: Annotated[Queue, Depends(get_queue)],
    x_github_event: Annotated[str, Header()],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict:
    secret = get_settings().github_webhook_secret.get_secret_value()
    if not verify_signature(secret, body, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    # Any verified delivery, including the ping GitHub sends when a webhook is created,
    # proves the repository is connected; the setup screen waits for this.
    _record_delivery(db, body)

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event {x_github_event}"}

    try:
        event = PullRequestEvent.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed pull_request payload") from None
    if event.action not in REVIEW_ACTIONS:
        return {"status": "ignored", "reason": f"action {event.action}"}

    repo = db.scalar(
        select(Repository).where(Repository.full_name == event.repository.full_name, Repository.is_active)
    )
    if repo is None:
        return {"status": "ignored", "reason": "repository not registered"}

    gh = event.pull_request
    pr = db.scalar(
        select(PullRequest).where(PullRequest.repository_id == repo.id, PullRequest.number == gh.number)
    )
    if pr is None:
        pr = PullRequest(repository=repo, number=gh.number)
        db.add(pr)
    pr.title, pr.author, pr.head_sha, pr.html_url = gh.title, gh.user.login, gh.head.sha, gh.html_url
    db.flush()

    existing = db.scalar(
        select(ReviewRun).where(ReviewRun.pull_request_id == pr.id, ReviewRun.head_sha == gh.head.sha)
    )
    if existing is not None:
        db.commit()
        return {"status": "duplicate", "run_id": existing.id}

    run = ReviewRun(pull_request=pr, head_sha=gh.head.sha)
    db.add(run)
    db.commit()
    enqueue_review(db, queue, run)
    return {"status": "queued", "run_id": run.id}
