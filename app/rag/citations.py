from __future__ import annotations

import re
from dataclasses import dataclass

GITHUB_URL_RE = re.compile(
    r"https://github\.com/[\w.-]+/[\w.-]+/"
    r"(?:blob/[A-Za-z0-9._-]+/[^\s\]\)>\"'`,#]+(?:#L\d+(?:-L\d+)?)?"
    r"|issues/\d+|pull/\d+)"
)
TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


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
    found = _extract_github_urls(answer)

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
    found = _extract_github_urls(answer)
    normalized_evidence = {_clean_url(url) for url in evidence_urls}

    valid: list[str] = []
    invalid: list[str] = []
    for url in found:
        if _is_supported_by_evidence(url, normalized_evidence):
            valid.append(url)
        else:
            invalid.append(url)

    return len(invalid) == 0, invalid


def _extract_github_urls(text: str) -> list[str]:
    return [_clean_url(match.group(0)) for match in GITHUB_URL_RE.finditer(text)]


def _clean_url(url: str) -> str:
    return url.rstrip(TRAILING_URL_PUNCTUATION)


def _is_supported_by_evidence(url: str, evidence_urls: set[str]) -> bool:
    if url in evidence_urls:
        return True
    url_base = _without_line_fragment(url)
    return any(url_base == _without_line_fragment(evidence) for evidence in evidence_urls)


def _without_line_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def _extract_title_from_url(url: str) -> str:
    issue_match = re.search(r"/issues/(\d+)$", url)
    if issue_match:
        return f"Issue #{issue_match.group(1)}"

    pr_match = re.search(r"/pull/(\d+)$", url)
    if pr_match:
        return f"PR #{pr_match.group(1)}"

    parts = url.split("/")
    if len(parts) >= 7:
        filename = parts[-1].split("#")[0]
        return filename or "unknown"
    return "unknown"


def _extract_path_from_url(url: str) -> str | None:
    match = re.match(
        r"https://github\.com/[^/]+/[^/]+/blob/[^/]+/(.+?)(?:#L\d+(?:-L\d+)?)?$",
        url,
    )
    if match:
        return match.group(1)
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
