"""Finds credentials committed in a PR. Works on the diff text, so it covers every
file type (Python, JavaScript, YAML, .env, ...) rather than only Python like Bandit."""

import re
from collections.abc import Iterable

from app.models import Severity
from app.services.analyzers import RawFinding
from app.services.diff import ChangedFile, added_line_texts

TOOL = "secrets"

# Provider formats are specific enough to flag wherever they appear.
KNOWN_FORMATS = [
    ("SEC-AWS", "AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "SEC-GITHUB",
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    ),
    ("SEC-STRIPE", "Stripe live key", re.compile(r"\b[sr]k[_-]live[_-][0-9A-Za-z]{16,}\b")),
    ("SEC-SLACK", "Slack token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b")),
    ("SEC-GOOGLE", "Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("SEC-ANTHROPIC", "Anthropic API key", re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}")),
    (
        "SEC-PRIVATE-KEY",
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
    ),
]

# Variable names that usually hold a credential: api_key, apiToken, DB_PASSWORD, clientSecret...
_NAME_WORDS = "|".join(
    [
        r"api[_-]?key",
        "apikey",
        "secret",
        "token",
        r"passw(?:or)?d",
        "pwd",
        r"access[_-]?key",
        r"private[_-]?key",
        "credential",
        r"auth[_-]?key",
    ]
)
_NAME = rf"[A-Za-z0-9_.-]*(?:{_NAME_WORDS})[A-Za-z0-9_.-]*"
# `name = "value"` / `name: 'value'` in code, YAML and JSON.
QUOTED_ASSIGNMENT = re.compile(rf"""(?i)["']?\b({_NAME})["']?\s*[:=]\s*["']([^"'\s]{{8,}})["']""")
# `NAME=value` in .env-style files, where values are usually unquoted.
ENV_ASSIGNMENT = re.compile(rf"""(?i)^\s*(?:export\s+)?({_NAME})\s*=\s*([^\s"'#]{{8,}})\s*$""")

# Values that are clearly not real credentials. Only applied to the name-based rules;
# a value in a provider's exact format is reported even if it says "example".
_PLACEHOLDER_HINTS = (
    "example",
    "placeholder",
    "changeme",
    "change-me",
    "your",
    "xxxx",
    "dummy",
    "redacted",
    "sample",
    "fake",
    "test",
    "<",
    ">",
    "${",
    "{{",
    "os.environ",
    "getenv",
    "process.env",
)


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(hint in lowered for hint in _PLACEHOLDER_HINTS):
        return True
    # A run of one repeated character ("********") or a value with no digits and no
    # mixed case reads as a word, not a key, e.g. token_type = "bearer_token".
    return len(set(lowered)) <= 2 or not (any(c.isdigit() for c in value) or value != value.lower())


def mask(value: str) -> str:
    """Show just enough to recognise the key, never the whole thing."""
    return f"{value[:4]}… ({len(value)} characters)"


def _advice(what: str) -> str:
    return (
        f"Remove the {what} from the code and load it from an environment variable or a secret "
        "manager. It is now in the git history, so revoke it and issue a new one."
    )


def scan_line(path: str, line_no: int, text: str) -> RawFinding | None:
    for rule_id, what, pattern in KNOWN_FORMATS:
        if match := pattern.search(text):
            return RawFinding(
                tool=TOOL,
                rule_id=rule_id,
                severity=Severity.critical,
                file_path=path,
                line=line_no,
                message=f"Hardcoded {what}: {mask(match.group(0))}",
                suggestion=_advice(what),
                confidence="high",
            )
    for pattern in (QUOTED_ASSIGNMENT, ENV_ASSIGNMENT):
        match = pattern.search(text)
        if match and not _is_placeholder(match.group(2)):
            name, value = match.group(1), match.group(2)
            return RawFinding(
                tool=TOOL,
                rule_id="SEC-GENERIC",
                severity=Severity.high,
                file_path=path,
                line=line_no,
                message=f"Hardcoded secret in `{name}`: {mask(value)}",
                suggestion=_advice("secret"),
                confidence="medium",
            )
    return None


def scan_secrets(files: Iterable[ChangedFile]) -> list[RawFinding]:
    """One finding per added line at most: the first, most specific rule wins."""
    findings = []
    for f in files:
        for line_no, text in added_line_texts(f.patch):
            if finding := scan_line(f.path, line_no, text):
                findings.append(finding)
    return findings
