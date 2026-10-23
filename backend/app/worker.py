"""Entry point for RQ jobs. Start a worker with:  rq worker reviews --url $REDIS_URL"""

from app.config import get_settings
from app.db import get_sessionmaker
from app.services.github import GitHubClient
from app.services.llm_review import LLMReviewer
from app.services.review import run_review


def review_job(run_id: int) -> None:
    llm = LLMReviewer() if get_settings().llm_review_enabled else None
    with get_sessionmaker()() as db:
        run_review(db, run_id, GitHubClient(), llm)
