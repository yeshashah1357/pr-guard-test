from fastapi import HTTPException, status
from rq import Queue
from sqlalchemy.orm import Session

from app.models import ReviewRun, RunStatus


def enqueue_review(db: Session, queue: Queue, run: ReviewRun) -> None:
    """Queue a committed run. If Redis is down the run is marked failed rather
    than left 'queued' forever, so it can be retried from the dashboard."""
    try:
        queue.enqueue("app.worker.review_job", run.id, job_timeout=600)
    except Exception as exc:
        run.status = RunStatus.failed
        run.error = f"Could not queue review: {exc}"
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Review queue unavailable") from exc
