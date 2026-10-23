from app.models import Repository, ReviewRun, RunStatus
from tests.conftest import pr_event, sign


def post(client, body: bytes, event="pull_request", signature=None):
    return client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": signature if signature is not None else sign(body),
            "Content-Type": "application/json",
        },
    )


def register_repo(db, name="acme/api"):
    db.add(Repository(full_name=name))
    db.commit()


def test_rejects_missing_or_wrong_signature(client):
    body = pr_event()
    assert post(client, body, signature="").status_code == 401
    assert post(client, body, signature=sign(body, "wrong-secret-wrong")).status_code == 401
    # Signature over different bytes than were sent.
    assert post(client, body, signature=sign(body + b" ")).status_code == 401


def test_ping(client):
    assert post(client, b"{}", event="ping").json() == {"status": "pong"}


def test_ignores_unregistered_repos_and_other_events(client, db):
    assert post(client, pr_event()).json()["reason"] == "repository not registered"
    assert post(client, b"{}", event="issues").json()["status"] == "ignored"
    register_repo(db)
    assert post(client, pr_event(action="closed")).json()["status"] == "ignored"


def test_malformed_payload(client):
    assert post(client, b'{"action": "opened"}').status_code == 400
    assert post(client, b"not json").status_code == 400


def test_opened_pr_creates_run_and_enqueues(client, db, queue):
    register_repo(db)
    response = post(client, pr_event())
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert queue.jobs == [("app.worker.review_job", (run_id,))]
    assert db.get(ReviewRun, run_id).status == RunStatus.queued


def test_redelivery_is_idempotent_but_new_commit_gets_new_run(client, db, queue):
    register_repo(db)
    first = post(client, pr_event()).json()
    again = post(client, pr_event()).json()
    assert again == {"status": "duplicate", "run_id": first["run_id"]}
    pushed = post(client, pr_event(action="synchronize", sha="b" * 40)).json()
    assert pushed["status"] == "queued" and pushed["run_id"] != first["run_id"]
    assert len(queue.jobs) == 2


def test_queue_outage_marks_run_failed(client, db, queue):
    register_repo(db)
    queue.fail = True
    assert post(client, pr_event()).status_code == 503
    run = db.query(ReviewRun).one()
    assert run.status == RunStatus.failed
    assert "Could not queue" in run.error
