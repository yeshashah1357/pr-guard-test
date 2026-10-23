import pytest

from app.config import get_settings
from app.deps import get_github
from app.main import app
from app.models import Repository
from app.services.github import GitHubError
from tests.conftest import sign


class FakeGitHub:
    def __init__(self, repos: dict | None = None, fail: bool = False):
        self.repos, self.fail = repos or {}, fail

    def get_repo(self, repo):
        if self.fail:
            raise GitHubError("503 from GitHub")
        return self.repos.get(repo)


@pytest.fixture
def github():
    fake = FakeGitHub({"acme/public": {"private": False}, "acme/secret": {"private": True}})
    app.dependency_overrides[get_github] = lambda: fake
    return fake


def check(client, headers, name):
    return client.post("/api/repos/check", json={"full_name": name}, headers=headers)


def test_check_and_setup_are_admin_only(client, viewer, github):
    assert check(client, viewer, "acme/public").status_code == 403
    assert client.get("/api/repos/setup", headers=viewer).status_code == 403


def test_check_reports_found_private_public_and_missing(client, admin, github):
    private = check(client, admin, "acme/secret").json()
    assert (private["found"], private["private"]) == (True, True)

    public = check(client, admin, "acme/public").json()
    assert public["found"] and "make sure your token includes" in public["message"]

    missing = check(client, admin, "acme/typo").json()
    assert not missing["found"] and "token access" in missing["message"]

    assert check(client, admin, "not a repo").status_code == 422


def test_check_flags_already_registered(client, admin, github, db):
    db.add(Repository(full_name="acme/public"))
    db.commit()
    assert check(client, admin, "acme/public").json()["already_registered"] is True


def test_check_without_token_or_when_github_fails(client, admin):
    app.dependency_overrides[get_github] = lambda: None
    assert "not configured" in check(client, admin, "acme/x").json()["message"]
    app.dependency_overrides[get_github] = lambda: FakeGitHub(fail=True)
    assert "GitHub error" in check(client, admin, "acme/x").json()["message"]


def test_setup_builds_the_webhook_url_and_never_returns_the_secret(client, admin, monkeypatch):
    assert client.get("/api/repos/setup", headers=admin).json()["webhook_url"] is None

    monkeypatch.setattr(get_settings(), "public_url", "https://prguard.example.com/")
    setup = client.get("/api/repos/setup", headers=admin).json()
    assert setup["webhook_url"] == "https://prguard.example.com/api/webhooks/github"
    secret = get_settings().github_webhook_secret.get_secret_value()
    assert secret not in str(setup)


def test_a_verified_ping_marks_the_repository_connected(client, admin, db):
    db.add(Repository(full_name="acme/api"))
    db.commit()
    body = b'{"zen": "Keep it simple.", "repository": {"full_name": "acme/api"}}'

    # An unsigned ping must not count as a connection.
    client.post("/api/webhooks/github", content=body, headers={"X-GitHub-Event": "ping"})
    assert client.get("/api/repos", headers=admin).json()[0]["last_event_at"] is None

    headers = {"X-GitHub-Event": "ping", "X-Hub-Signature-256": sign(body)}
    assert client.post("/api/webhooks/github", content=body, headers=headers).json() == {"status": "pong"}
    assert client.get("/api/repos", headers=admin).json()[0]["last_event_at"] is not None
