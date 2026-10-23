from typing import Protocol

import httpx

from app.config import get_settings


class GitHubError(Exception):
    pass


class GitHub(Protocol):
    def list_pr_files(self, repo: str, number: int) -> list[dict]: ...
    def get_file_content(self, repo: str, path: str, ref: str) -> str | None: ...
    def create_review(
        self, repo: str, number: int, commit_id: str, body: str, comments: list[dict]
    ) -> int: ...


class GitHubClient:
    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        token = token or (settings.github_token.get_secret_value() if settings.github_token else None)
        if not token:
            raise GitHubError("GITHUB_TOKEN is not configured")
        self._http = httpx.Client(
            base_url=base_url or settings.github_api_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    def _get(self, url: str, **kwargs) -> httpx.Response:
        response = self._http.get(url, **kwargs)
        if response.status_code >= 400:
            raise GitHubError(f"GET {url} -> {response.status_code}: {response.text[:300]}")
        return response

    def list_pr_files(self, repo: str, number: int) -> list[dict]:
        files: list[dict] = []
        page = 1
        while True:
            batch = self._get(
                f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100, "page": page}
            ).json()
            files.extend(batch)
            if len(batch) < 100:
                return files
            page += 1

    def get_file_content(self, repo: str, path: str, ref: str) -> str | None:
        response = self._http.get(
            f"/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise GitHubError(f"contents {path} -> {response.status_code}")
        return response.text

    def create_review(self, repo: str, number: int, commit_id: str, body: str, comments: list[dict]) -> int:
        url = f"/repos/{repo}/pulls/{number}/reviews"
        payload = {"commit_id": commit_id, "event": "COMMENT", "body": body, "comments": comments}
        response = self._http.post(url, json=payload)
        if response.status_code == 422 and comments:
            # GitHub rejects the whole review if any comment's line isn't in the diff
            # (e.g. the PR moved on). Fall back to a summary-only review.
            response = self._http.post(url, json={**payload, "comments": []})
        if response.status_code >= 400:
            raise GitHubError(f"create review -> {response.status_code}: {response.text[:300]}")
        return response.json()["id"]
