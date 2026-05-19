#!/usr/bin/env python3
"""Ingest a GitHub repository into RepoRAG.

Usage:
    python scripts/ingest_repo.py --repo https://github.com/pallets/click --dry-run
    python scripts/ingest_repo.py --repo https://github.com/pallets/click
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from datetime import datetime, timezone

from app.core.logging import setup_logging
from app.db.models import Chunk, Document, Repository
from app.db.session import get_sync_session
from app.github.client import (
    FetchedFile,
    FetchedIssue,
    FetchedPullRequest,
    FetchResult,
    GitHubClient,
    parse_repo_url,
)
from app.ingestion.chunkers import (
    ChunkingResult,
    chunk_code_file,
    chunk_markdown,
    chunk_text_blocks,
)
from app.ingestion.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest a GitHub repository into RepoRAG",
    )
    parser.add_argument(
        "--repo", "-r", required=True,
        help="GitHub repository URL (e.g., https://github.com/pallets/click)",
    )
    parser.add_argument(
        "--branch", default=None, help="Branch to index (defaults to default branch)",
    )
    parser.add_argument(
        "--no-issues", action="store_true", help="Skip indexing issues",
    )
    parser.add_argument(
        "--no-pull-requests", action="store_true", help="Skip indexing PRs",
    )
    parser.add_argument(
        "--max-issues", type=int, default=30,
        help="Maximum number of issues to index (default: 30)",
    )
    parser.add_argument(
        "--max-pull-requests", type=int, default=30,
        help="Maximum number of pull requests to index (default: 30)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch repo contents but do not insert into database",
    )
    return parser


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _print_dry_run(repo_info, file_paths, issues, pull_requests) -> None:
    print(f"\nRepository: {repo_info.owner}/{repo_info.name}")
    print(f"  URL: {repo_info.url}")
    print(f"  Branch: {repo_info.default_branch}")
    print(f"  Latest commit: {repo_info.latest_commit}")
    print(f"\nFiles matched: {len(file_paths)}")
    for p in file_paths[:10]:
        print(f"  - {p}")
    if len(file_paths) > 10:
        print(f"  ... and {len(file_paths) - 10} more")
    print(f"\nIssues fetched: {len(issues)}")
    for i in issues[:5]:
        print(f"  - #{i.number}: {i.title}")
    if len(issues) > 5:
        print(f"  ... and {len(issues) - 5} more")
    print(f"\nPull requests fetched: {len(pull_requests)}")
    for pr in pull_requests[:5]:
        print(f"  - #{pr.number}: {pr.title}")
    if len(pull_requests) > 5:
        print(f"  ... and {len(pull_requests) - 5} more")


def _do_ingest(result: FetchResult) -> str:
    session = get_sync_session()

    try:
        repo = Repository(
            owner=result.repo_info.owner,
            name=result.repo_info.name,
            url=result.repo_info.url,
            default_branch=result.repo_info.default_branch,
            last_indexed_commit=result.repo_info.latest_commit,
            indexed_at=datetime.now(timezone.utc),
            status="indexing",
        )
        session.add(repo)
        session.flush()

        doc_count = 0
        chunk_count = 0

        if result.readme:
            doc = _create_document(repo, result.readme, "file")
            session.add(doc)
            session.flush()
            chunks = _chunk_markdown_doc(repo, doc, result.readme)
            session.add_all(chunks)
            session.flush()
            doc_count += 1
            chunk_count += len(chunks)
            logger.info("Indexed README: %d chunks", len(chunks))

        for fetched_file in result.files:
            doc = _create_document(repo, fetched_file, "file")
            session.add(doc)
            session.flush()
            chunks = _chunk_file(repo, doc, fetched_file)
            session.add_all(chunks)
            session.flush()
            doc_count += 1
            chunk_count += len(chunks)

        all_chunks = (
            session.query(Chunk)
            .filter(Chunk.repo_id == repo.id)
            .all()
        )
        if all_chunks:
            embedding_client = EmbeddingClient()
            texts = [c.content for c in all_chunks]
            embeddings = embedding_client.embed(texts)
            for chunk, vector in zip(all_chunks, embeddings):
                chunk.embedding = vector
            session.flush()
            logger.info("Embedded %d chunks", len(all_chunks))

        for issue in result.issues:
            doc = _create_issue_document(repo, issue)
            session.add(doc)
            session.flush()
            chunks = _chunk_issue(repo, doc, issue)
            session.add_all(chunks)
            session.flush()
            doc_count += 1
            chunk_count += len(chunks)

        for pr in result.pull_requests:
            doc = _create_pr_document(repo, pr)
            session.add(doc)
            session.flush()
            chunks = _chunk_pr(repo, doc, pr)
            session.add_all(chunks)
            session.flush()
            doc_count += 1
            chunk_count += len(chunks)

        new_chunks = (
            session.query(Chunk)
            .filter(Chunk.repo_id == repo.id, Chunk.embedding.is_(None))
            .all()
        )
        if new_chunks:
            embedding_client = EmbeddingClient()
            texts = [c.content for c in new_chunks]
            embeddings = embedding_client.embed(texts)
            for chunk, vector in zip(new_chunks, embeddings):
                chunk.embedding = vector
            session.flush()
            logger.info("Embedded %d issue/PR chunks", len(new_chunks))

        repo.status = "completed"
        repo.indexed_at = datetime.now(timezone.utc)
        session.commit()

        print(f"\nIngestion complete for {repo.owner}/{repo.name}")
        print(f"  Repo ID: {repo.id}")
        print(f"  Documents: {doc_count}")
        print(f"  Chunks: {chunk_count}")
        return repo.id

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _create_document(repo: Repository, f: FetchedFile, source_type: str) -> Document:
    return Document(
        repo_id=repo.id, source_type=source_type,
        path=f.path, url=f.url, commit_sha=f.commit_sha,
        title=f.path, content_hash=f.content_hash,
    )


def _create_issue_document(repo: Repository, issue: FetchedIssue) -> Document:
    return Document(
        repo_id=repo.id, source_type="issue",
        url=issue.url,
        title=f"#{issue.number}: {issue.title}",
        content_hash=_hash(issue.title + issue.body),
    )


def _create_pr_document(repo: Repository, pr: FetchedPullRequest) -> Document:
    return Document(
        repo_id=repo.id, source_type="pull_request",
        url=pr.url,
        title=f"#{pr.number}: {pr.title}",
        content_hash=_hash(pr.title + pr.body),
    )


def _chunk_markdown_doc(
    repo: Repository, doc: Document, f: FetchedFile,
) -> list[Chunk]:
    results = chunk_markdown(f.content, f.path, f.commit_sha, f.url)
    return [_result_to_chunk(repo.id, doc.id, r) for r in results]


def _chunk_file(repo: Repository, doc: Document, f: FetchedFile) -> list[Chunk]:
    results = chunk_code_file(f.content, f.path, f.commit_sha, f.url)
    return [_result_to_chunk(repo.id, doc.id, r) for r in results]


def _chunk_issue(
    repo: Repository, doc: Document, issue: FetchedIssue,
) -> list[Chunk]:
    text = f"#{issue.number}: {issue.title}\n\n{issue.body}"
    results = chunk_text_blocks(text, None, doc.url or "", "issue_comment")
    return [_result_to_chunk(repo.id, doc.id, r) for r in results]


def _chunk_pr(repo: Repository, doc: Document, pr: FetchedPullRequest) -> list[Chunk]:
    text = f"#{pr.number}: {pr.title}\n\n{pr.body}"
    results = chunk_text_blocks(text, None, doc.url or "", "pr_description")
    return [_result_to_chunk(repo.id, doc.id, r) for r in results]


def _result_to_chunk(repo_id: str, doc_id: str, r: ChunkingResult) -> Chunk:
    return Chunk(
        document_id=doc_id, repo_id=repo_id,
        chunk_type=r.chunk_type, content=r.content,
        summary=r.summary, path=r.path, symbol_name=r.symbol_name,
        line_start=r.line_start, line_end=r.line_end,
        github_url=r.github_url, metadata_json=r.metadata,
    )


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    owner, name = parse_repo_url(args.repo)

    client = GitHubClient()
    logger.info("Fetching repo info for %s/%s...", owner, name)
    repo_info = client.fetch_repo_info(owner, name, branch=args.branch)

    issues: list[FetchedIssue] = []
    if not args.no_issues:
        logger.info("Fetching issues...")
        issues = client.fetch_issues(owner, name, max_count=args.max_issues)

    pull_requests: list[FetchedPullRequest] = []
    if not args.no_pull_requests:
        logger.info("Fetching pull requests...")
        pull_requests = client.fetch_pull_requests(
            owner, name, max_count=args.max_pull_requests,
        )

    if args.dry_run:
        file_paths = client.fetch_file_list(owner, name, repo_info.latest_commit)
        _print_dry_run(repo_info, file_paths, issues, pull_requests)
        return

    files, readme = client.fetch_files(owner, name, repo_info.latest_commit)

    result = FetchResult(
        repo_info=repo_info, readme=readme, files=files,
        issues=issues, pull_requests=pull_requests,
    )

    _do_ingest(result)


if __name__ == "__main__":
    main()
