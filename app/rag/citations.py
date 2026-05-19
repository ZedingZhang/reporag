from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Citation:
    title: str
    url: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


def build_github_permalink(
    owner: str,
    repo: str,
    commit_sha: str,
    path: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    url = f"https://github.com/{owner}/{repo}/blob/{commit_sha}/{path}"
    if line_start and line_end and line_start != line_end:
        return f"{url}#L{line_start}-L{line_end}"
    elif line_start:
        return f"{url}#L{line_start}"
    return url


def build_issue_url(owner: str, repo: str, number: int) -> str:
    return f"https://github.com/{owner}/{repo}/issues/{number}"


def build_pr_url(owner: str, repo: str, number: int) -> str:
    return f"https://github.com/{owner}/{repo}/pull/{number}"


def extract_citations_from_answer(
    answer: str, valid_urls: set[str]
) -> list[Citation]:
    url_pattern = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/blob/[a-f0-9]+/[^\s\)]+(?:#L\d+(?:-L\d+)?)?")
    found = url_pattern.findall(answer)

    citations: list[Citation] = []
    seen: set[str] = set()
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        citations.append(Citation(
            title=_extract_title_from_url(url),
            url=url,
            path=_extract_path_from_url(url),
            line_start=_extract_line_start(url),
            line_end=_extract_line_end(url),
        ))
    return citations


def validate_citations(
    answer: str, evidence_urls: set[str]
) -> tuple[bool, list[str]]:
    url_pattern = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/blob/[a-f0-9]+/[^\s\)]+(?:#L\d+(?:-L\d+)?)?")
    found = url_pattern.findall(answer)

    valid: list[str] = []
    invalid: list[str] = []
    for url in found:
        if url in evidence_urls or any(url.startswith(e) for e in evidence_urls):
            valid.append(url)
        else:
            invalid.append(url)

    return len(invalid) == 0, invalid


def _extract_title_from_url(url: str) -> str:
    parts = url.split("/")
    if len(parts) >= 7:
        filename = parts[-1].split("#")[0]
        return filename or "unknown"
    return "unknown"


def _extract_path_from_url(url: str) -> str | None:
    parts = url.split("/")
    if len(parts) >= 7:
        return "/".join(parts[5:]).split("#")[0]
    return None


def _extract_line_start(url: str) -> int | None:
    match = re.search(r"#L(\d+)", url)
    if match:
        return int(match.group(1))
    return None


def _extract_line_end(url: str) -> int | None:
    match = re.search(r"L(\d+)-L(\d+)$", url)
    if match:
        return int(match.group(2))
    return None
