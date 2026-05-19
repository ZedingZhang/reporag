from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    IndexRepoRequest,
    IndexRepoResponse,
    RepoInfo,
    RepoListResponse,
    RetrievedChunk,
)
from app.db.models import Repository
from app.db.session import get_sync_session

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_ingestion(
    repo_id: str,
    repo_url: str,
    branch: str | None = None,
    include_issues: bool = True,
    include_pull_requests: bool = True,
    max_issues: int = 30,
    max_pull_requests: int = 30,
) -> None:
    from app.db.models import Chunk, Document
    from app.github.client import GitHubClient, parse_repo_url
    from app.ingestion.chunkers import chunk_code_file, chunk_markdown, chunk_text_blocks
    from app.ingestion.embeddings import EmbeddingClient

    session = get_sync_session()
    try:
        repo = session.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            logger.error("Repo %s not found for ingestion", repo_id)
            return

        repo.status = "indexing"
        session.commit()

        owner, name = parse_repo_url(repo_url)
        client = GitHubClient()
        repo_info = client.fetch_repo_info(owner, name, branch=branch)
        repo.default_branch = repo_info.default_branch
        repo.last_indexed_commit = repo_info.latest_commit
        session.commit()

        files, readme = client.fetch_files(owner, name, repo_info.latest_commit)

        issues = []
        if include_issues:
            issues = client.fetch_issues(owner, name, max_count=max_issues)

        pull_requests = []
        if include_pull_requests:
            pull_requests = client.fetch_pull_requests(
                owner, name, max_count=max_pull_requests,
            )

        def _hash(text: str) -> str:
            import hashlib
            return hashlib.sha256(text.encode()).hexdigest()

        def _add_chunks_from_chunking_results(
            doc_id: str, results: list, repo_id_str: str,
        ) -> None:
            for r in results:
                session.add(Chunk(
                    document_id=doc_id, repo_id=repo_id_str,
                    chunk_type=r.chunk_type, content=r.content,
                    summary=r.summary, path=r.path, symbol_name=r.symbol_name,
                    line_start=r.line_start, line_end=r.line_end,
                    github_url=r.github_url, metadata_json=r.metadata,
                ))

        # README
        if readme:
            doc = Document(
                repo_id=repo_id, source_type="file",
                path=readme.path, url=readme.url,
                commit_sha=readme.commit_sha, title=readme.path,
                content_hash=readme.content_hash,
            )
            session.add(doc)
            session.flush()
            _add_chunks_from_chunking_results(
                doc.id,
                chunk_markdown(
                    readme.content, readme.path,
                    readme.commit_sha, readme.url,
                ),
                repo_id,
            )

        # Files
        for f in files:
            doc = Document(
                repo_id=repo_id, source_type="file",
                path=f.path, url=f.url, commit_sha=f.commit_sha,
                title=f.path, content_hash=f.content_hash,
            )
            session.add(doc)
            session.flush()
            _add_chunks_from_chunking_results(
                doc.id,
                chunk_code_file(f.content, f.path, f.commit_sha, f.url),
                repo_id,
            )

        session.flush()

        # Issues
        for issue in issues:
            doc = Document(
                repo_id=repo_id, source_type="issue",
                url=issue.url,
                title=f"#{issue.number}: {issue.title}",
                content_hash=_hash(issue.title + issue.body),
            )
            session.add(doc)
            session.flush()
            text = f"#{issue.number}: {issue.title}\n\n{issue.body}"
            _add_chunks_from_chunking_results(
                doc.id,
                chunk_text_blocks(text, None, issue.url, "issue_comment"),
                repo_id,
            )

        # PRs
        for pr in pull_requests:
            doc = Document(
                repo_id=repo_id, source_type="pull_request",
                url=pr.url,
                title=f"#{pr.number}: {pr.title}",
                content_hash=_hash(pr.title + pr.body),
            )
            session.add(doc)
            session.flush()
            text = f"#{pr.number}: {pr.title}\n\n{pr.body}"
            _add_chunks_from_chunking_results(
                doc.id,
                chunk_text_blocks(text, None, pr.url, "pr_description"),
                repo_id,
            )

        # Embed
        embedding_client = EmbeddingClient()
        all_chunks = session.query(Chunk).filter(
            Chunk.repo_id == repo_id, Chunk.embedding.is_(None),
        ).all()
        if all_chunks:
            texts = [c.content for c in all_chunks]
            embeddings = embedding_client.embed(texts)
            for c, vec in zip(all_chunks, embeddings):
                c.embedding = vec
            logger.info("Embedded %d chunks for repo %s", len(all_chunks), repo_id)

        repo.status = "completed"
        repo.indexed_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("Ingestion complete for %s", repo_url)

    except Exception:
        session.rollback()
        try:
            repo = session.query(Repository).filter(Repository.id == repo_id).first()
            if repo:
                repo.status = "failed"
                session.commit()
        except Exception:
            pass
        logger.exception("Ingestion failed for %s", repo_url)
    finally:
        session.close()


@router.post("/repos/index", response_model=IndexRepoResponse)
async def index_repo(
    request: IndexRepoRequest, background_tasks: BackgroundTasks,
) -> IndexRepoResponse:
    from app.github.client import GitHubClient, parse_repo_url

    try:
        owner, name = parse_repo_url(request.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session = get_sync_session()
    try:
        existing = (
            session.query(Repository)
            .filter(Repository.owner == owner, Repository.name == name)
            .first()
        )
        if existing and existing.status == "completed":
            return IndexRepoResponse(
                repo_id=existing.id, status=existing.status,
                message="Repository already indexed.",
            )
        if existing and existing.status == "indexing":
            return IndexRepoResponse(
                repo_id=existing.id, status="indexing",
                message="Indexing already in progress.",
            )

        client = GitHubClient()
        repo_info = client.fetch_repo_info(owner, name, branch=request.branch)

        if existing:
            existing.status = "pending"
            existing.last_indexed_commit = repo_info.latest_commit
            session.commit()
            repo_id = existing.id
        else:
            repo = Repository(
                owner=owner, name=name, url=repo_info.url,
                default_branch=repo_info.default_branch,
                last_indexed_commit=repo_info.latest_commit,
                status="pending",
            )
            session.add(repo)
            session.commit()
            repo_id = repo.id

        background_tasks.add_task(
            _run_ingestion,
            repo_id,
            request.repo_url,
            request.branch,
            request.include_issues,
            request.include_pull_requests,
            request.max_issues,
            request.max_pull_requests,
        )

        return IndexRepoResponse(
            repo_id=repo_id, status="indexing",
            message="Indexing started in background.",
        )
    except Exception as e:
        session.rollback()
        logger.exception("Failed to start indexing")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/repos", response_model=RepoListResponse)
async def list_repos() -> RepoListResponse:
    session = get_sync_session()
    try:
        repos = (
            session.query(Repository)
            .order_by(Repository.created_at.desc()).all()
        )
        return RepoListResponse(repos=[
            RepoInfo(
                id=r.id, owner=r.owner, name=r.name, url=r.url,
                default_branch=r.default_branch,
                last_indexed_commit=r.last_indexed_commit,
                indexed_at=r.indexed_at, status=r.status,
            )
            for r in repos
        ])
    finally:
        session.close()


@router.get("/repos/{repo_id}/status", response_model=RepoInfo)
async def get_repo_status(repo_id: str) -> RepoInfo:
    session = get_sync_session()
    try:
        repo = session.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        return RepoInfo(
            id=repo.id, owner=repo.owner, name=repo.name, url=repo.url,
            default_branch=repo.default_branch,
            last_indexed_commit=repo.last_indexed_commit,
            indexed_at=repo.indexed_at, status=repo.status,
        )
    finally:
        session.close()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = get_sync_session()
    try:
        repo = session.query(Repository).filter(
            Repository.id == request.repo_id,
        ).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        if repo.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Repository not ready (status: {repo.status}).",
            )

        from app.core.providers import get_chat_provider
        from app.ingestion.embeddings import EmbeddingClient
        from app.rag.graph import build_rag_graph
        from app.retrieval.hybrid import HybridRetriever

        chat_provider = get_chat_provider()
        embedding_client = EmbeddingClient()
        retriever = HybridRetriever(session, embedding_client)
        graph = build_rag_graph(chat_provider, retriever)

        initial_state = {
            "repo_id": request.repo_id,
            "question": request.question,
            "top_k": request.top_k,
        }
        result = graph.invoke(initial_state)

        citations = [
            Citation(
                title=c.title, url=c.url,
                path=c.path, line_start=c.line_start, line_end=c.line_end,
            )
            for c in result["citations"]
        ]

        retrieved_chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id,
                content=c.content[:500],
                path=c.path,
                chunk_type=c.chunk_type,
                score=round(c.score, 4),
            )
            for c in result["reranked_chunks"]
        ]

        return ChatResponse(
            answer=result["answer"],
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence=result["confidence"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
