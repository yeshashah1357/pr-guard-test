import httpx
import pytest

from app.services.github import GitHubClient, GitHubError


def client_with(handler) -> GitHubClient:
    gh = GitHubClient(token="test-token", base_url="https://api.github.test")
    gh._http = httpx.Client(base_url="https://api.github.test", transport=httpx.MockTransport(handler))
    return gh


def test_missing_token_is_an_error(monkeypatch):
    with pytest.raises(GitHubError, match="GITHUB_TOKEN"):
        GitHubClient()


def test_list_pr_files_follows_pagination():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        count = 100 if page == 1 else 3
        return httpx.Response(200, json=[{"filename": f"f{page}-{i}.py"} for i in range(count)])

    assert len(client_with(handler).list_pr_files("acme/api", 7)) == 103


def test_get_file_content_handles_missing_files_and_errors():
    responses = {"present.py": httpx.Response(200, text="print(1)"), "gone.py": httpx.Response(404)}

    def handler(request):
        name = request.url.path.rsplit("/", 1)[-1]
        assert request.url.params["ref"] == "abc"
        return responses.get(name, httpx.Response(500))

    gh = client_with(handler)
    assert gh.get_file_content("acme/api", "present.py", "abc") == "print(1)"
    assert gh.get_file_content("acme/api", "gone.py", "abc") is None
    with pytest.raises(GitHubError):
        gh.get_file_content("acme/api", "broken.py", "abc")


def test_create_review_falls_back_to_summary_when_lines_are_rejected():
    bodies = []

    def handler(request):
        import json

        payload = json.loads(request.content)
        bodies.append(payload)
        if payload["comments"]:
            return httpx.Response(422, json={"message": "line must be part of the diff"})
        return httpx.Response(200, json={"id": 42})

    review_id = client_with(handler).create_review(
        "acme/api", 7, "sha", "summary", [{"path": "a.py", "line": 1}]
    )
    assert review_id == 42
    assert [len(b["comments"]) for b in bodies] == [1, 0]


def test_create_review_raises_on_server_error():
    gh = client_with(lambda request: httpx.Response(502, text="bad gateway"))
    with pytest.raises(GitHubError, match="502"):
        gh.create_review("acme/api", 7, "sha", "summary", [])
