"""Offline demo: runs the real review pipeline on sample pull requests, with no
GitHub account, token or API key. Fills the dashboard so you can try it out.

    python -m app.demo            (or: docker compose exec api python -m app.demo)
"""

import hashlib
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import PullRequest, Repository, ReviewRun, Role, User
from app.security import hash_password
from app.services.llm_review import LLMReviewer
from app.services.review import run_review

log = logging.getLogger(__name__)

DEMO_REPO = "demo/sample-shop"

SAMPLE_PRS = [
    (
        "Add order export endpoint",
        "app/export.py",
        """\
import pickle
import subprocess

import requests


def export_orders(path):
    subprocess.call(f"zip -r out.zip {path}", shell=True)
    return open(path).read()


def load_cache(blob):
    return pickle.loads(blob)


def fetch_rates():
    return requests.get("https://api.example.com/rates", verify=False).json()
""",
    ),
    (
        "Add login helpers",
        "app/auth.py",
        """\
import hashlib
import random

SECRET_KEY = "super-secret-key-123"


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def make_reset_token():
    return str(random.random())


def is_admin(user, roles=[]):
    try:
        return user.is_admin
    except Exception:
        pass
""",
    ),
    (
        "Add user report query",
        "app/reports.py",
        """\
import sqlite3


def find_user(conn: sqlite3.Connection, name: str):
    query = "SELECT * FROM users WHERE name = '%s'" % name
    return conn.execute(query).fetchall()


def run_formula(expression):
    return eval(expression)


def total(rows):
    return sum(row.amount for row in rws)
""",
    ),
]


def _new_file_patch(content: str) -> str:
    lines = content.splitlines()
    return f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(f"+{line}" for line in lines)


class LocalGitHub:
    """Serves one sample PR in place of the GitHub API and keeps the review it would post."""

    def __init__(self, path: str, content: str) -> None:
        self.path, self.content = path, content
        self.posted: list[str] = []

    def list_pr_files(self, repo: str, number: int) -> list[dict]:
        return [{"filename": self.path, "status": "added", "patch": _new_file_patch(self.content)}]

    def get_file_content(self, repo: str, path: str, ref: str) -> str | None:
        return self.content if path == self.path else None

    def create_review(self, repo: str, number: int, commit_id: str, body: str, comments: list[dict]) -> int:
        self.posted.append(body)
        return len(self.posted)


def _ensure_admin(db: Session) -> None:
    email, password = os.environ.get("DEMO_ADMIN_EMAIL"), os.environ.get("DEMO_ADMIN_PASSWORD")
    if not email or not password:
        return
    if db.scalar(select(User).where(User.email == email.lower())) is None:
        db.add(User(email=email.lower(), hashed_password=hash_password(password), role=Role.admin))
        db.commit()
        log.info("created demo admin %s", email)


def seed(db: Session, llm: LLMReviewer | None = None) -> int:
    """Review each sample PR once. Safe to run repeatedly. Returns the number of new runs."""
    _ensure_admin(db)
    repo = db.scalar(select(Repository).where(Repository.full_name == DEMO_REPO))
    if repo is None:
        repo = Repository(full_name=DEMO_REPO)
        db.add(repo)
        db.commit()

    created = 0
    for number, (title, path, content) in enumerate(SAMPLE_PRS, start=1):
        sha = hashlib.sha1(content.encode(), usedforsecurity=False).hexdigest()
        pr = db.scalar(
            select(PullRequest).where(PullRequest.repository_id == repo.id, PullRequest.number == number)
        )
        if pr is None:
            pr = PullRequest(
                repository=repo,
                number=number,
                title=title,
                author="demo-user",
                head_sha=sha,
            )
            db.add(pr)
        # The sample PRs don't exist on GitHub, so they get no link.
        pr.html_url = ""
        db.commit()
        if db.scalar(select(ReviewRun).where(ReviewRun.pull_request_id == pr.id, ReviewRun.head_sha == sha)):
            continue
        run = ReviewRun(pull_request=pr, head_sha=sha)
        db.add(run)
        db.commit()
        run_review(db, run.id, LocalGitHub(path, content), llm)
        db.refresh(run)
        log.info("PR #%d %r: %d finding(s)", number, title, len(run.findings))
        created += 1
    return created


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    llm = LLMReviewer() if get_settings().llm_review_enabled else None
    with get_sessionmaker()() as db:
        created = seed(db, llm)
    print(f"Demo ready: {created} new review run(s) for {DEMO_REPO}.")


if __name__ == "__main__":
    main()
