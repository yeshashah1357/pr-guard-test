import json
from types import SimpleNamespace

import anthropic
import httpx

from app.models import Severity
from app.services.diff import ChangedFile
from app.services.llm_review import LLMReviewer

FILES = [ChangedFile.from_patch("app/x.py", "@@ -0,0 +1,2 @@\n+import os\n+os.system(cmd)")]


def response(payload=None, stop_reason="end_turn", stop_details=None):
    text = json.dumps(payload if payload is not None else {"findings": []})
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=stop_details,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_parses_findings_and_sends_structured_request():
    client = FakeClient(
        response(
            {
                "findings": [
                    {
                        "file_path": "app/x.py",
                        "line": 2,
                        "severity": "critical",
                        "title": "Command injection",
                        "explanation": "cmd is user input",
                        "suggestion": "use subprocess.run([...])",
                    }
                ]
            }
        )
    )
    findings, note = LLMReviewer(client=client).review(FILES)

    assert note is None
    assert [(f.line, f.severity, f.tool) for f in findings] == [(2, Severity.critical, "llm")]
    assert findings[0].message.startswith("Command injection:")

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "    2 +os.system(cmd)" in call["messages"][0]["content"]
    assert "untrusted" in call["system"]


def test_refusal_and_truncation_return_no_findings_with_a_note():
    refused = response(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    assert LLMReviewer(client=FakeClient(refused)).review(FILES) == (
        [],
        "LLM declined to review (category: cyber)",
    )
    truncated = response(stop_reason="max_tokens")
    findings, note = LLMReviewer(client=FakeClient(truncated)).review(FILES)
    assert findings == [] and "output limit" in note


def test_api_errors_do_not_raise():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for exc, expected in [
        (
            anthropic.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None),
            "rate limited",
        ),
        (
            anthropic.InternalServerError("boom", response=httpx.Response(500, request=request), body=None),
            "HTTP 500",
        ),
        (anthropic.APIConnectionError(request=request), "connection error"),
    ]:
        findings, note = LLMReviewer(client=FakeClient(exc)).review(FILES)
        assert findings == [] and expected in note


def test_invalid_output_is_reported_not_raised():
    bad = response({"findings": [{"file_path": "x", "line": "two"}]})
    assert LLMReviewer(client=FakeClient(bad)).review(FILES) == ([], "LLM output could not be parsed")


def test_oversized_diffs_are_skipped_not_truncated(monkeypatch):
    reviewer = LLMReviewer(client=FakeClient(response()))
    reviewer.max_chars = 10
    findings, note = reviewer.review(FILES)
    assert findings == [] and "app/x.py" in note
    assert reviewer.client.calls == []
