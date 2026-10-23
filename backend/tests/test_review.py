import pytest

from app.models import PullRequest, Repository, ReviewRun, RunStatus, Severity
from app.services.analyzers import RawFinding
from app.services.github import GitHubError
from app.services.review import run_review

SOURCE = """\
import subprocess


def old(cmd):
    return subprocess.call(cmd, shell=True)


def new(cmd):
    return subprocess.call(cmd, shell=True)
"""
# The PR only adds lines 6-9, so the identical call on line 5 must not be reported.
PATCH = """\
@@ -4,2 +4,6 @@ def old(cmd):
 def old(cmd):
     return subprocess.call(cmd, shell=True)
+
+
+def new(cmd):
+    return subprocess.call(cmd, shell=True)"""


class FakeGitHub:
    def __init__(self, files=None, contents=None, fail_review=False):
        self.files = (
            files
            if files is not None
            else [
                {"filename": "app/tasks.py", "status": "modified", "patch": PATCH},
                {"filename": "README.md", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"},
                {"filename": "gone.py", "status": "removed", "patch": "@@ -1 +0,0 @@\n-x"},
                {"filename": "../escape.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+x"},
            ]
        )
        self.contents = contents if contents is not None else {"app/tasks.py": SOURCE}
        self.fail_review = fail_review
        self.reviews: list[dict] = []

    def list_pr_files(self, repo, number):
        return self.files

    def get_file_content(self, repo, path, ref):
        return self.contents.get(path)

    def create_review(self, repo, number, commit_id, body, comments):
        if self.fail_review:
            raise GitHubError("502 from GitHub")
        self.reviews.append({"commit_id": commit_id, "body": body, "comments": comments})
        return 1


class FakeLLM:
    def __init__(self, findings=None, note=None):
        self.findings, self.note = findings or [], note
        self.seen_paths: list[str] = []

    def review(self, files):
        self.seen_paths = [f.path for f in files]
        return self.findings, self.note


@pytest.fixture
def run(db):
    repo = Repository(full_name="acme/api")
    pr = PullRequest(
        repository=repo,
        number=7,
        title="t",
        author="octocat",
        head_sha="c" * 40,
        html_url="https://github.com/acme/api/pull/7",
    )
    run = ReviewRun(pull_request=pr, head_sha="c" * 40)
    db.add(run)
    db.commit()
    return run


def test_reports_only_added_lines_and_dedupes_across_tools(db, run):
    github = FakeGitHub()
    run_review(db, run.id, github, FakeLLM())
    db.refresh(run)

    assert run.status == RunStatus.completed
    # Ruff S602 and Bandit B602 flag the same line; one finding survives, from Bandit.
    shell = [f for f in run.findings if f.line == 9]
    assert [(f.tool, f.rule_id) for f in shell] == [("bandit", "B602")]
    assert all(f.line in {6, 7, 8, 9} for f in run.findings)
    assert "Skipped file with unsafe path" in run.notes

    [review] = github.reviews
    assert review["commit_id"] == "c" * 40
    assert review["comments"][0]["path"] == "app/tasks.py" and review["comments"][0]["side"] == "RIGHT"
    assert "PR Guard found" in review["body"]


def test_llm_sees_all_text_files_and_its_findings_are_filtered(db, run):
    llm = FakeLLM(
        findings=[
            RawFinding(
                "llm", "llm-review", Severity.critical, "app/tasks.py", 9, "Shell injection", "Pass a list"
            ),
            RawFinding("llm", "llm-review", Severity.high, "app/tasks.py", 2, "Not an added line"),
            RawFinding("llm", "llm-review", Severity.high, "invented.py", 1, "Hallucinated file"),
        ],
        note="LLM skipped 1 file(s)",
    )
    run_review(db, run.id, FakeGitHub(), llm)
    db.refresh(run)

    assert sorted(llm.seen_paths) == ["README.md", "app/tasks.py"]
    llm_findings = [f for f in run.findings if f.tool == "llm"]
    assert [(f.line, f.severity) for f in llm_findings] == [(9, Severity.critical)]
    assert "LLM skipped" in run.notes


def test_comment_cap_keeps_most_severe(db, run, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_review_comments", 1)
    github = FakeGitHub()
    minor = RawFinding("llm", "llm-review", Severity.low, "app/tasks.py", 8, "Missing docstring")
    run_review(db, run.id, github, FakeLLM(findings=[minor]))
    db.refresh(run)
    [review] = github.reviews
    assert len(review["comments"]) == 1
    assert "[HIGH]" in review["comments"][0]["body"]
    assert "most severe inline" in review["body"]


def test_clean_pr(db, run):
    github = FakeGitHub(files=[{"filename": "docs.md", "status": "added", "patch": "@@ -0,0 +1 @@\n+hi"}])
    run_review(db, run.id, github, None)
    db.refresh(run)
    assert run.findings == []
    assert "no issues" in github.reviews[0]["body"]
    assert "LLM review is disabled" in run.notes


def test_github_outage_while_posting_keeps_findings(db, run):
    run_review(db, run.id, FakeGitHub(fail_review=True), FakeLLM())
    db.refresh(run)
    assert run.status == RunStatus.completed
    assert run.findings
    assert "could not be posted" in run.error


def test_failure_marks_run_failed_and_reraises(db, run):
    class Broken(FakeGitHub):
        def list_pr_files(self, repo, number):
            raise GitHubError("401 bad credentials")

    with pytest.raises(GitHubError):
        run_review(db, run.id, Broken(), None)
    db.refresh(run)
    assert run.status == RunStatus.failed
    assert "bad credentials" in run.error


def test_missing_run_is_a_noop(db):
    run_review(db, 12345, FakeGitHub(), None)
