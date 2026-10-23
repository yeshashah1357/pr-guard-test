import jwt

from app.config import get_settings
from tests.conftest import auth_headers


def register(client, email, password="password123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def test_first_user_is_admin_and_later_users_are_viewers(client):
    assert register(client, "first@example.com").json()["role"] == "admin"
    assert register(client, "second@example.com").json()["role"] == "viewer"


def test_duplicate_email_is_rejected_case_insensitively(client):
    register(client, "dup@example.com")
    assert register(client, "DUP@example.com").status_code == 409


def test_short_password_is_rejected(client):
    assert register(client, "x@example.com", "short").status_code == 422


def test_login_and_me(client):
    register(client, "me@example.com")
    headers = auth_headers(client, "me@example.com")
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_wrong_password_and_unknown_email_get_the_same_error(client):
    register(client, "me@example.com")
    wrong = client.post("/api/auth/login", data={"username": "me@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", data={"username": "who@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_tampered_and_expired_tokens_are_rejected(client):
    register(client, "me@example.com")
    forged = jwt.encode({"sub": "1", "exp": 9999999999}, "not-the-secret-not-the-secret-!!", "HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    secret = get_settings().jwt_secret.get_secret_value()
    expired = jwt.encode({"sub": "1", "exp": 1}, secret, "HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_no_token_is_rejected(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_is_rate_limited(client):
    limit = get_settings().login_rate_limit_per_minute
    for _ in range(limit):
        client.post("/api/auth/login", data={"username": "a@example.com", "password": "whatever1"})
    response = client.post("/api/auth/login", data={"username": "a@example.com", "password": "whatever1"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
