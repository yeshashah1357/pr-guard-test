import os

# Settings are read at import time, so the test environment is set first.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-characters"
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["LLM_REVIEW_ENABLED"] = "false"

import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.deps import get_queue, get_redis  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []
        self.fail = False

    def enqueue(self, func, *args, **kwargs):
        if self.fail:
            raise ConnectionError("redis down")
        self.jobs.append((func, args))


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def queue():
    return FakeQueue()


@pytest.fixture
def client(session_factory, queue):
    def override_db():
        with session_factory() as session:
            yield session

    redis = fakeredis.FakeRedis()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_queue] = lambda: queue
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth_headers(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def make_user(client, session_factory):
    """Register a user, force their role, and return auth headers."""

    def _make(email: str, role: Role) -> dict:
        client.post("/api/auth/register", json={"email": email, "password": "password123"})
        with session_factory() as s:
            user = s.query(User).filter_by(email=email).one()
            user.role = role
            s.commit()
        return auth_headers(client, email)

    return _make


@pytest.fixture
def admin(make_user):
    return make_user("admin@example.com", Role.admin)


@pytest.fixture
def viewer(make_user):
    return make_user("viewer@example.com", Role.viewer)


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def pr_event(action="opened", repo="acme/api", number=7, sha="a" * 40) -> bytes:
    return json.dumps(
        {
            "action": action,
            "repository": {"full_name": repo},
            "pull_request": {
                "number": number,
                "title": "Add payments endpoint",
                "html_url": f"https://github.com/{repo}/pull/{number}",
                "user": {"login": "octocat"},
                "head": {"sha": sha},
            },
        }
    ).encode()
