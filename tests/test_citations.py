from __future__ import annotations

from app.rag.citations import (
    Citation,
    build_github_permalink,
    build_issue_url,
    build_pr_url,
    extract_citations_from_answer,
    validate_citations,
)


class TestBuildPermalink:
    def test_basic_permalink(self) -> None:
        url = build_github_permalink(
            owner="pallets",
            repo="click",
            commit_sha="abc123def456",
            path="src/click/core.py",
        )
        assert url == "https://github.com/pallets/click/blob/abc123def456/src/click/core.py"

    def test_permalink_with_line_range(self) -> None:
        url = build_github_permalink(
            owner="pallets",
            repo="click",
            commit_sha="abc123",
            path="src/core.py",
            line_start=10,
            line_end=42,
        )
        assert url.endswith("#L10-L42")

    def test_permalink_single_line(self) -> None:
        url = build_github_permalink(
            owner="pallets",
            repo="click",
            commit_sha="abc123",
            path="src/core.py",
            line_start=5,
            line_end=5,
        )
        assert url.endswith("#L5")

    def test_permalink_uses_commit_not_branch(self) -> None:
        url = build_github_permalink(
            owner="pallets",
            repo="click",
            commit_sha="abc123def456",
            path="docs/index.md",
        )
        assert "/blob/abc123def456/" in url
        assert "/blob/main/" not in url


class TestIssueAndPRUrls:
    def test_issue_url(self) -> None:
        url = build_issue_url("pallets", "click", 42)
        assert url == "https://github.com/pallets/click/issues/42"

    def test_pr_url(self) -> None:
        url = build_pr_url("pallets", "click", 100)
        assert url == "https://github.com/pallets/click/pull/100"


class TestExtractCitations:
    def test_extracts_github_urls(self) -> None:
        answer = (
            "The command parsing is in "
            "https://github.com/pallets/click/blob/abc/src/click/core.py#L10-L42 "
            "and also related to "
            "https://github.com/pallets/click/blob/abc/src/click/utils.py#L5"
        )
        citations = extract_citations_from_answer(answer, set())
        assert len(citations) == 2

    def test_deduplicates_urls(self) -> None:
        answer = (
            "See https://github.com/pallets/click/blob/abc/src/core.py#L10 "
            "and also https://github.com/pallets/click/blob/abc/src/core.py#L10"
        )
        citations = extract_citations_from_answer(answer, set())
        assert len(citations) == 1

    def test_empty_answer(self) -> None:
        citations = extract_citations_from_answer("No specific file referenced.", set())
        assert len(citations) == 0


class TestValidateCitations:
    def test_all_valid(self) -> None:
        evidence = {
            "https://github.com/pallets/click/blob/abc/src/core.py#L10",
            "https://github.com/pallets/click/blob/abc/src/utils.py",
        }
        answer = (
            "Check https://github.com/pallets/click/blob/abc/src/core.py#L10-L20 "
            "and https://github.com/pallets/click/blob/abc/src/utils.py"
        )
        is_valid, invalid = validate_citations(answer, evidence)
        assert is_valid
        assert len(invalid) == 0

    def test_detects_fabricated_citations(self) -> None:
        evidence = {
            "https://github.com/pallets/click/blob/abc/src/core.py",
        }
        answer = (
            "Check https://github.com/pallets/click/blob/abc/src/core.py "
            "and https://github.com/pallets/click/blob/abc/src/fake.py"
        )
        is_valid, invalid = validate_citations(answer, evidence)
        assert not is_valid
        assert len(invalid) >= 1
        assert "fake.py" in invalid[0]

    def test_partial_match(self) -> None:
        evidence = {
            "https://github.com/pallets/click/blob/abc/src/core.py",
        }
        answer = "See https://github.com/pallets/click/blob/abc/src/core.py#L10-L42"
        is_valid, invalid = validate_citations(answer, evidence)
        assert is_valid
        assert len(invalid) == 0

    def test_empty_answer(self) -> None:
        is_valid, invalid = validate_citations("", set())
        assert is_valid
        assert len(invalid) == 0
