from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IssueCommentResult:
    success: bool
    url: str = ""
    error: str = ""


@dataclass
class PullRequestResult:
    success: bool
    url: str = ""
    error: str = ""


def create_issue_comment(
    owner: str, repo: str, issue_number: int, body: str,
    token: str | None = None,
) -> IssueCommentResult:
    logger.info(
        "create_issue_comment placeholder: %s/%s#%d",
        owner, repo, issue_number,
    )
    return IssueCommentResult(
        success=False,
        error="GitHub write operations not yet implemented (Phase 8+). "
              "Requires GITHUB_TOKEN with repo scope and approval.",
    )


def create_pull_request(
    owner: str, repo: str, title: str, body: str,
    head: str, base: str = "main",
    token: str | None = None,
) -> PullRequestResult:
    logger.info(
        "create_pull_request placeholder: %s/%s %s→%s",
        owner, repo, head, base,
    )
    return PullRequestResult(
        success=False,
        error="GitHub write operations not yet implemented (Phase 8+). "
              "Requires GITHUB_TOKEN with repo scope and approval.",
    )
