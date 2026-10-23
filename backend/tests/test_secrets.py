import pytest

from app.models import Severity
from app.services.diff import ChangedFile
from app.services.secrets import mask, scan_line, scan_secrets

# Built from pieces so this file never contains a full key-shaped string, which would
# trip GitHub's push protection on this repository.
GITHUB_PAT = "github_" + "pat_" + "A1b2C3d4" * 10
STRIPE_LIVE = "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc"
AWS_KEY = "AKIA" + "Z7Q2LMN4PX6RT8VB"
SLACK = "xox" + "b-1234567890-abcdefABCDEF"
PRIVATE_KEY = "-----BEGIN RSA " + "PRIVATE KEY-----"


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        (f'token = "{GITHUB_PAT}"', "SEC-GITHUB"),
        (f"stripe.api_key = '{STRIPE_LIVE}'", "SEC-STRIPE"),
        (f"aws_access_key_id={AWS_KEY}", "SEC-AWS"),
        (f"SLACK = {SLACK}", "SEC-SLACK"),
        (PRIVATE_KEY, "SEC-PRIVATE-KEY"),
    ],
)
def test_known_provider_formats_are_critical(line, rule):
    finding = scan_line("app/config.py", 3, line)
    assert finding.rule_id == rule
    assert (finding.severity, finding.confidence) == (Severity.critical, "high")


@pytest.mark.parametrize(
    "line",
    [
        'API_KEY = "a8f5f167f44f4964"',
        "const apiToken = 'a8f5f167f44f4964e6c9';",  # JavaScript
        'db_password: "Pr0d-Pa55w0rd!"',  # YAML
        "DATABASE_PASSWORD=Xk29mQ7vLp",  # .env, unquoted
        '{"clientSecret": "9f8e7d6c5b4a3210"}',  # JSON
    ],
)
def test_secret_looking_assignments_in_any_language(line):
    finding = scan_line("any.file", 1, line)
    assert finding is not None, line
    assert (finding.rule_id, finding.severity) == ("SEC-GENERIC", Severity.high)


@pytest.mark.parametrize(
    "line",
    [
        'API_KEY = os.environ["API_KEY"]',
        'api_key = "your-api-key-here"',
        'password = "changeme123"',
        'token = "${GITHUB_TOKEN}"',
        'secret = "********"',
        'token_type = "bearer_token"',  # a word, not a key
        'password = "short1"',  # too short to be a real credential
        "API_KEY=",
    ],
)
def test_placeholders_and_lookups_are_ignored(line):
    assert scan_line("app/config.py", 1, line) is None


def test_the_key_bandit_missed_on_the_live_pr_is_caught_as_stripe():
    finding = scan_line("examples/refunds.py", 8, 'API_KEY = "sk-live-1234567890abcdef"')
    assert (finding.rule_id, finding.severity) == ("SEC-STRIPE", Severity.critical)


def test_the_secret_is_masked_in_the_message():
    finding = scan_line("a.py", 1, 'API_KEY = "sk-live-1234567890abcdef"')
    assert "sk-live-1234567890abcdef" not in finding.message
    assert mask("sk-live-1234567890abcdef") in finding.message
    assert "revoke" in finding.suggestion


def test_scans_only_added_lines_of_every_file_type():
    patch = "@@ -1,2 +1,3 @@\n-OLD_SECRET=Ab12Cd34Ef\n KEEP=1\n+NEW_SECRET=Zz98Yy76Xx\n+DEBUG=true"
    findings = scan_secrets([ChangedFile.from_patch("deploy/.env.production", patch)])
    assert [(f.file_path, f.line) for f in findings] == [("deploy/.env.production", 2)]
