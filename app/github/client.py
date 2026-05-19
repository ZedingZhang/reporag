from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


RATE_LIMIT_WARNING_THRESHOLD = 20

TARGET_EXTENSIONS = {
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
}


@dataclass
class RepoInfo:
    owner: str
    name: str
    url: str
    default_branch: str
    latest_commit: str


@dataclass
class FetchedFile:
    path: str
    url: str
    content: str
    commit_sha: str
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class FetchedIssue:
    number: int
    title: str
    body: str
    state: str
    author: str
    created_at: str
    updated_at: str
    url: str


@dataclass
class FetchedPullRequest:
    number: int
    title: str
    body: str
    state: str
    author: str
    created_at: str
    updated_at: str
    url: str


@dataclass
class FetchResult:
    repo_info: RepoInfo
    readme: FetchedFile | None = None
    files: list[FetchedFile] = field(default_factory=list)
    issues: list[FetchedIssue] = field(default_factory=list)
    pull_requests: list[FetchedPullRequest] = field(default_factory=list)


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.github_token
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RepoRAG",
        }
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"

    def _check_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining and int(remaining) < RATE_LIMIT_WARNING_THRESHOLD:
            logger.warning(
                "GitHub API rate limit low: %s remaining. "
                "Set GITHUB_TOKEN to increase limit.",
                remaining,
            )

    def _request(self, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            response = httpx.get(url, headers=self._headers, timeout=30, **kwargs)
        except httpx.HTTPError as e:
            raise RuntimeError(f"GitHub API request failed: {url}") from e
        self._check_rate_limit(response)
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError(
                "GitHub API rate limit exceeded. Set GITHUB_TOKEN to increase the limit."
            )
        if response.status_code == 404:
            raise RuntimeError(f"GitHub resource not found: {url}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def fetch_repo_info(self, owner: str, name: str) -> RepoInfo:
        data = self._request(f"/repos/{owner}/{name}")
        default_branch = data.get("default_branch", "main")
        latest_commit = self._get_latest_commit(owner, name, default_branch)
        return RepoInfo(
            owner=owner,
            name=name,
            url=data["html_url"],
            default_branch=default_branch,
            latest_commit=latest_commit,
        )

    def _get_latest_commit(self, owner: str, name: str, branch: str) -> str:
        data = self._request(f"/repos/{owner}/{name}/branches/{branch}")
        return data["commit"]["sha"]

    def fetch_file_list(
        self, owner: str, name: str, commit_sha: str
    ) -> list[str]:
        tree_data = self._request(
            f"/repos/{owner}/{name}/git/trees/{commit_sha}?recursive=1"
        )
        if tree_data.get("truncated"):
            logger.warning(
                "Repository tree is truncated. Some files may be missing."
            )

        paths: list[str] = []
        for item in tree_data.get("tree", []):
            if item["type"] != "blob":
                continue
            ext = self._get_extension(item["path"])
            if ext in TARGET_EXTENSIONS:
                paths.append(item["path"])
        return paths

    def fetch_files(
        self, owner: str, name: str, commit_sha: str
    ) -> tuple[list[FetchedFile], FetchedFile | None]:
        paths = self.fetch_file_list(owner, name, commit_sha)

        files: list[FetchedFile] = []
        readme: FetchedFile | None = None

        for path in paths:

            content = self._fetch_file_content(owner, name, path, commit_sha)
            if content is None:
                continue

            fetched = FetchedFile(
                path=path,
                url=self._build_permalink(owner, name, commit_sha, path),
                content=content,
                commit_sha=commit_sha,
            )

            if path.lower() == "readme.md":
                readme = fetched
            else:
                files.append(fetched)

        return files, readme

    def _fetch_file_content(
        self, owner: str, name: str, path: str, ref: str
    ) -> str | None:
        import base64

        try:
            data = self._request(
                f"/repos/{owner}/{name}/contents/{path}", params={"ref": ref}
            )
            content = data.get("content", "")
            if data.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8", errors="replace")
            return content
        except RuntimeError:
            logger.warning("Failed to fetch content for %s", path)
            return None

    def fetch_issues(
        self, owner: str, name: str, max_count: int = 30
    ) -> list[FetchedIssue]:
        issues: list[FetchedIssue] = []
        page = 1
        while len(issues) < max_count:
            data = self._request(
                f"/repos/{owner}/{name}/issues",
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": min(100, max_count),
                    "page": page,
                },
            )
            if not data:
                break
            for item in data:
                if "pull_request" in item:
                    continue
                issues.append(
                    FetchedIssue(
                        number=item["number"],
                        title=item["title"],
                        body=item.get("body") or "",
                        state=item["state"],
                        author=item["user"]["login"] if item.get("user") else "unknown",
                        created_at=item["created_at"],
                        updated_at=item["updated_at"],
                        url=item["html_url"],
                    )
                )
            page += 1
        return issues[:max_count]

    def fetch_pull_requests(
        self, owner: str, name: str, max_count: int = 30
    ) -> list[FetchedPullRequest]:
        prs: list[FetchedPullRequest] = []
        page = 1
        while len(prs) < max_count:
            data = self._request(
                f"/repos/{owner}/{name}/pulls",
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": min(100, max_count),
                    "page": page,
                },
            )
            if not data:
                break
            for item in data:
                prs.append(
                    FetchedPullRequest(
                        number=item["number"],
                        title=item["title"],
                        body=item.get("body") or "",
                        state=item["state"],
                        author=item["user"]["login"] if item.get("user") else "unknown",
                        created_at=item["created_at"],
                        updated_at=item["updated_at"],
                        url=item["html_url"],
                    )
                )
            page += 1
        return prs[:max_count]

    def _get_extension(self, path: str) -> str:
        import os
        _, ext = os.path.splitext(path.lower())
        return ext

    def _build_permalink(
        self, owner: str, name: str, commit_sha: str, path: str
    ) -> str:
        return f"https://github.com/{owner}/{name}/blob/{commit_sha}/{path}"


def parse_repo_url(url: str) -> tuple[str, str]:
    patterns = [
        r"github\.com[:/]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?$",
        r"github\.com[:/]([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?/",
    ]
    cleaned = url.strip().rstrip("/")
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(1), match.group(2)
    raise ValueError(
        f"Cannot parse GitHub repository URL: {url}. "
        f"Expected format: https://github.com/owner/name"
    )
