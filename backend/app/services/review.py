import logging
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SEVERITY_RANK, Finding, ReviewRun, RunStatus
from app.services.analyzers import RawFinding, run_bandit, run_ruff
from app.services.diff import ChangedFile, is_safe_path
from app.services.github import GitHub, GitHubError
from app.services.llm_review import LLMReviewer
from app.services.secrets import scan_secrets

log = logging.getLogger(__name__)

# Lower wins when two tools report the same issue on the same line.
TOOL_PRIORITY = {"secrets": 0, "bandit": 1, "ruff": 2, "llm": 3}


def _keep(findings: list[RawFinding], changed: dict[str, ChangedFile]) -> list[RawFinding]:
    """Drop findings outside the lines this PR added, and collapse duplicates
    (the same issue reported by two tools), keeping the most specific tool."""
    best: dict[tuple, RawFinding] = {}
    for f in findings:
        file = changed.get(f.file_path)
        if file is None or f.line not in file.added_lines:
            continue
        current = best.get(f.dedupe_key)
        if current is None or TOOL_PRIORITY[f.tool] < TOOL_PRIORITY[current.tool]:
            best[f.dedupe_key] = f
    return sorted(best.values(), key=lambda f: (-SEVERITY_RANK[f.severity], f.file_path, f.line))


def _comment_body(f: RawFinding) -> str:
    body = f"**[{f.severity.upper()}] {f.tool} `{f.rule_id}`**"
    if f.confidence:
        body += f" ({f.confidence} confidence)"
    body += f"\n\n{f.message}"
    if f.suggestion:
        body += f"\n\n**Suggestion:** {f.suggestion}"
    return body


def _summary(findings: list[RawFinding], notes: list[str], posted: int) -> str:
    counts = Counter(f.severity for f in findings)
    if findings:
        breakdown = ", ".join(f"{counts[s]} {s}" for s in sorted(counts, key=SEVERITY_RANK.get, reverse=True))
        text = f"### PR Guard found {len(findings)} issue(s): {breakdown}"
        if posted < len(findings):
            text += f"\n\nShowing the {posted} most severe inline; the rest are on the dashboard."
    else:
        text = "### PR Guard found no issues in the added lines"
    if notes:
        text += "\n\n" + "\n".join(f"- {n}" for n in notes)
    return text


def run_review(db: Session, run_id: int, github: GitHub, llm: LLMReviewer | None) -> None:
    run = db.get(ReviewRun, run_id)
    if run is None:
        log.warning("run %s no longer exists", run_id)
        return
    pr = run.pull_request
    repo = pr.repository.full_name
    settings = get_settings()

    run.status, run.started_at, run.error = RunStatus.running, datetime.now(UTC), None
    db.commit()

    try:
        notes: list[str] = []
        files = github.list_pr_files(repo, pr.number)
        if len(files) > settings.max_files_per_review:
            notes.append(f"Reviewed the first {settings.max_files_per_review} of {len(files)} files")
            files = files[: settings.max_files_per_review]

        changed: dict[str, ChangedFile] = {}
        for f in files:
            if f["status"] == "removed" or not f.get("patch"):
                continue
            if not is_safe_path(f["filename"]):
                notes.append(f"Skipped file with unsafe path: {f['filename']!r}")
                continue
            changed[f["filename"]] = ChangedFile.from_patch(f["filename"], f["patch"])

        # The secret scan reads the diff itself, so it covers every changed file type.
        found: list[RawFinding] = scan_secrets(changed.values())
        python_files = [p for p in changed if p.endswith(".py")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = []
            for path in python_files:
                content = github.get_file_content(repo, path, run.head_sha)
                if content is None:
                    continue
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                written.append(path)
            found += run_ruff(root, written)
            found += run_bandit(root, written)

        if llm is not None:
            llm_findings, note = llm.review(list(changed.values()))
            found += llm_findings
            if note:
                notes.append(note)
        else:
            notes.append("LLM review is disabled")

        kept = _keep(found, changed)
        run.findings = [
            Finding(
                tool=f.tool,
                rule_id=f.rule_id,
                severity=f.severity,
                file_path=f.file_path,
                line=f.line,
                message=f.message,
                suggestion=f.suggestion,
                confidence=f.confidence,
            )
            for f in kept
        ]
        run.notes = "\n".join(notes) or None
        run.status, run.finished_at = RunStatus.completed, datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        run.status, run.finished_at = RunStatus.failed, datetime.now(UTC)
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        raise

    # Findings are saved before posting, so a GitHub outage loses nothing.
    inline = kept[: settings.max_review_comments]
    comments = [
        {"path": f.file_path, "line": f.line, "side": "RIGHT", "body": _comment_body(f)} for f in inline
    ]
    try:
        github.create_review(repo, pr.number, run.head_sha, _summary(kept, notes, len(inline)), comments)
    except GitHubError as exc:
        run.error = f"Findings saved, but the review could not be posted: {exc}"
        db.commit()
