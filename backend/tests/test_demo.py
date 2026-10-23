from app.demo import seed
from app.models import Finding, PullRequest, Repository, Role, Severity, User


def test_demo_reviews_samples_once_and_creates_admin(db, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_EMAIL", "Demo@Example.com")
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "demo-password-1")

    assert seed(db) == 3
    rules = {f.rule_id for f in db.query(Finding)}
    # Shell injection, unsafe pickle, MD5, SQL injection and eval are all caught.
    assert {"B602", "B301", "B324", "B608", "B307"} <= rules
    sql = db.query(Finding).filter_by(rule_id="B608").one()
    assert (sql.severity, sql.confidence) == (Severity.high, "low")
    assert db.query(User).filter_by(email="demo@example.com").one().role == Role.admin

    # The sample PRs aren't on GitHub, so the dashboard must not link to them.
    assert {pr.html_url for pr in db.query(PullRequest)} == {""}

    assert seed(db) == 0
    assert db.query(Repository).count() == 1
