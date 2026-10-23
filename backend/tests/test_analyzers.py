from pathlib import Path

from app.models import Severity
from app.services.analyzers import RawFinding, _bandit_severity, run_bandit, run_ruff

VULNERABLE = """\
import subprocess

password = "hunter2"


def run(cmd):
    return subprocess.call(cmd, shell=True)


def unused():
    return undefined_name
"""


def write(tmp_path: Path) -> list[str]:
    target = tmp_path / "pkg" / "tasks.py"
    target.parent.mkdir()
    target.write_text(VULNERABLE)
    return ["pkg/tasks.py"]


def test_ruff_reports_relative_paths_and_maps_severity(tmp_path):
    findings = run_ruff(tmp_path, write(tmp_path))
    by_rule = {f.rule_id: f for f in findings}
    assert by_rule["F821"].line == 11 and by_rule["F821"].severity == Severity.medium
    assert by_rule["S602"].severity == Severity.high
    assert all(f.file_path == "pkg/tasks.py" for f in findings)


def test_bandit_finds_shell_injection(tmp_path):
    findings = run_bandit(tmp_path, write(tmp_path))
    shell = next(f for f in findings if f.rule_id == "B602")
    assert shell.line == 7 and shell.severity == Severity.high
    assert shell.file_path == "pkg/tasks.py"


def test_no_files_means_no_subprocess(tmp_path):
    assert run_ruff(tmp_path, []) == [] and run_bandit(tmp_path, []) == []


def test_bandit_severity_is_kept_and_injection_is_raised_to_high():
    assert _bandit_severity("B324", "HIGH") == Severity.high
    assert _bandit_severity("B311", "LOW") == Severity.low
    assert _bandit_severity("B608", "MEDIUM") == Severity.high
    # An override only ever raises a rating.
    assert _bandit_severity("B608", "HIGH") == Severity.high


def test_low_confidence_sql_injection_is_reported_high_with_its_confidence(tmp_path):
    (tmp_path / "q.py").write_text(
        # The query built into a variable first is what Bandit scores as low confidence.
        "def find(conn, name):\n    query = \"SELECT * FROM t WHERE n = '%s'\" % name\n    return conn.execute(query)\n"
    )
    [sql] = [f for f in run_bandit(tmp_path, ["q.py"]) if f.rule_id == "B608"]
    assert sql.severity == Severity.high
    assert sql.confidence == "low"


def test_ruff_s_rules_dedupe_with_bandit_b_rules():
    ruff = RawFinding("ruff", "S602", Severity.high, "a.py", 7, "")
    bandit = RawFinding("bandit", "B602", Severity.high, "a.py", 7, "")
    assert ruff.dedupe_key == bandit.dedupe_key
