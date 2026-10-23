from datetime import UTC, datetime, timedelta

import pytest

from app.models import Finding, PullRequest, Repository, ReviewRun, RunStatus, Severity


@pytest.fixture
def seeded(db):
    now = datetime.now(UTC)
    api, web = Repository(full_name="acme/api"), Repository(full_name="acme/web")
    runs = []
    for repo, number in ((api, 1), (web, 2)):
        pr = PullRequest(
            repository=repo,
            number=number,
            title="t",
            author="a",
            head_sha="d" * 40,
            html_url=f"https://github.com/{repo.full_name}/pull/{number}",
        )
        runs.append(ReviewRun(pull_request=pr, head_sha="d" * 40, status=RunStatus.completed))
    db.add_all(runs)
    db.flush()

    def finding(run, severity, tool, days_ago):
        return Finding(
            run_id=run.id,
            tool=tool,
            rule_id="R1",
            severity=severity,
            file_path="a.py",
            line=1,
            message="m",
            created_at=now - timedelta(days=days_ago),
        )

    db.add_all(
        [
            finding(runs[0], Severity.high, "bandit", 0),
            finding(runs[0], Severity.high, "llm", 0),
            finding(runs[0], Severity.low, "ruff", 1),
            finding(runs[1], Severity.critical, "llm", 0),
            finding(runs[1], Severity.medium, "ruff", 90),
        ]
    )
    db.commit()
    return api, web, runs


def test_requires_auth(client):
    assert client.get("/api/findings").status_code == 401


def test_filters_and_pagination(client, viewer, seeded):
    api, _, _ = seeded
    page = client.get("/api/findings", params={"limit": 2}, headers=viewer).json()
    assert page["total"] == 5 and len(page["items"]) == 2

    high = client.get("/api/findings", params={"severity": ["high", "critical"]}, headers=viewer).json()
    assert high["total"] == 3

    api_llm = client.get("/api/findings", params={"repo_id": api.id, "tool": "llm"}, headers=viewer).json()
    assert api_llm["total"] == 1
    assert api_llm["items"][0]["repository"] == "acme/api"
    assert api_llm["items"][0]["pr_url"].endswith("/pull/1")

    assert client.get("/api/findings", params={"limit": 500}, headers=viewer).status_code == 422


def test_trends_group_by_day_and_severity(client, viewer, seeded):
    api, _, _ = seeded
    points = client.get("/api/stats/trends", params={"days": 30}, headers=viewer).json()
    # The 90-day-old finding falls outside the window.
    assert sum(p["count"] for p in points) == 4
    today = datetime.now(UTC).date().isoformat()
    assert {"day": today, "severity": "high", "count": 2} in points

    api_only = client.get("/api/stats/trends", params={"repo_id": api.id}, headers=viewer).json()
    assert sum(p["count"] for p in api_only) == 3


def test_pulls_and_run_detail(client, viewer, seeded):
    api, _, runs = seeded
    pulls = client.get(f"/api/repos/{api.id}/pulls", headers=viewer).json()
    assert pulls[0]["number"] == 1 and pulls[0]["latest_run"]["status"] == "completed"

    detail = client.get(f"/api/runs/{runs[0].id}", headers=viewer).json()
    assert len(detail["findings"]) == 3
    assert detail["pull_request"]["repository_name"] == "acme/api"
    assert detail["pull_request"]["html_url"].endswith("/pull/1")
    assert pulls[0]["repository_name"] == "acme/api"
    assert client.get("/api/runs/999", headers=viewer).status_code == 404


def test_rerun_requires_reviewer_and_requeues(client, viewer, make_user, seeded, queue):
    _, _, runs = seeded
    assert client.post(f"/api/runs/{runs[0].id}/rerun", headers=viewer).status_code == 403

    from app.models import Role

    reviewer = make_user("rev@example.com", Role.reviewer)
    response = client.post(f"/api/runs/{runs[0].id}/rerun", headers=reviewer)
    assert response.status_code == 202
    assert response.json()["status"] == "queued" and response.json()["findings"] == []
    assert queue.jobs == [("app.worker.review_job", (runs[0].id,))]
    # A second rerun while the first is still queued is refused.
    assert client.post(f"/api/runs/{runs[0].id}/rerun", headers=reviewer).status_code == 409
    assert client.post("/api/runs/999/rerun", headers=reviewer).status_code == 404
