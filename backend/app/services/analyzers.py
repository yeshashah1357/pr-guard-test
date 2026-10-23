"""Static analyzers. Both only parse source files — neither imports or executes
the PR's code — which is what makes it safe to run them on untrusted input."""

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.models import SEVERITY_RANK, Severity

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120
HARDCODED_SECRET_RULES = {"B105", "B106", "B107"}


@dataclass
class RawFinding:
    tool: str
    rule_id: str
    severity: Severity
    file_path: str
    line: int
    message: str
    suggestion: str | None = None
    # How sure the tool is that this is a real issue (Bandit reports it); None if unknown.
    confidence: str | None = None

    @property
    def dedupe_key(self) -> tuple[str, int, str]:
        # Ruff's S-rules are ports of Bandit's B-rules (S105 == B105); treat them as one.
        rule = (
            "B" + self.rule_id[1:] if self.tool == "ruff" and self.rule_id.startswith("S") else self.rule_id
        )
        # Bandit's hardcoded-password checks and the secret scanner describe the same problem.
        if rule in HARDCODED_SECRET_RULES or self.tool == "secrets":
            rule = "hardcoded-secret"
        return self.file_path, self.line, rule


def _relative(root: Path, filename: str) -> str:
    # Ruff reports absolute paths, Bandit reports them relative to its cwd (root).
    path = Path(filename)
    if not path.is_absolute():
        path = root / path
    return path.resolve().relative_to(root.resolve()).as_posix()


def _run(args: list[str], root: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    # Both tools exit 1 when they find issues, so only a crash is an error.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[:500]}")
    return result.stdout


def _ruff_severity(code: str) -> Severity:
    if code.startswith("S"):
        return Severity.high
    if code.startswith(("F", "B")):
        return Severity.medium
    return Severity.low


def run_ruff(root: Path, files: list[str]) -> list[RawFinding]:
    if not files:
        return []
    out = _run(
        [
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "json",
            "--select",
            "E9,F,B,S,W6",
            "--exit-zero",
            *files,
        ],
        root,
    )
    return [
        RawFinding(
            tool="ruff",
            rule_id=item["code"] or "syntax",
            severity=_ruff_severity(item["code"] or "F"),
            file_path=_relative(root, item["filename"]),
            line=item["location"]["row"],
            message=item["message"],
            suggestion=(item.get("fix") or {}).get("message"),
        )
        for item in json.loads(out or "[]")
    ]


# Injection lets an attacker run their own SQL or code, so it is rated by impact. Bandit
# rates these MEDIUM; Ruff's ports (S608, S307, S102) are already HIGH via _ruff_severity.
SEVERITY_OVERRIDES = {
    "B608": Severity.high,  # SQL built from strings
    "B307": Severity.high,  # eval()
    "B102": Severity.high,  # exec()
}


def _bandit_severity(test_id: str, severity: str) -> Severity:
    # Confidence is reported alongside, never folded in: a likely SQL injection is still
    # a SQL injection, and lowering it would hide the riskiest findings.
    level = Severity(severity.lower())
    override = SEVERITY_OVERRIDES.get(test_id)
    return override if override and SEVERITY_RANK[override] > SEVERITY_RANK[level] else level


def run_bandit(root: Path, files: list[str]) -> list[RawFinding]:
    if not files:
        return []
    out = _run(["bandit", "-f", "json", "-q", *files], root)
    report = json.loads(out or "{}")
    for err in report.get("errors", []):
        log.warning("bandit could not scan %s: %s", err.get("filename"), err.get("reason"))
    return [
        RawFinding(
            tool="bandit",
            rule_id=item["test_id"],
            severity=_bandit_severity(item["test_id"], item["issue_severity"]),
            file_path=_relative(root, item["filename"]),
            line=item["line_number"],
            message=item["issue_text"],
            confidence=item["issue_confidence"].lower(),
        )
        for item in report.get("results", [])
    ]
