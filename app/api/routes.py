from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    IndexRepoRequest,
    IndexRepoResponse,
    RepoInfo,
    RepoListResponse,
)
from app.db.models import Repository
from app.db.session import get_sync_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/repos/index", response_model=IndexRepoResponse)
async def index_repo(request: IndexRepoRequest) -> IndexRepoResponse:
    from app.github.client import GitHubClient, parse_repo_url, FetchResult

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
        if existing:
            return IndexRepoResponse(
                repo_id=existing.id,
                status=existing.status,
                message=f"Repository already indexed (status: {existing.status})",
            )

        client = GitHubClient()
        repo_info = client.fetch_repo_info(owner, name)

        repo = Repository(
            owner=owner,
            name=name,
            url=repo_info.url,
            default_branch=repo_info.default_branch,
            last_indexed_commit=repo_info.latest_commit,
            status="pending",
        )
        session.add(repo)
        session.commit()

        return IndexRepoResponse(
            repo_id=repo.id,
            status="pending",
            message=f"Repository registered. Use scripts/ingest_repo.py to index: "
            f"python scripts/ingest_repo.py --repo {request.repo_url}",
        )
    except Exception as e:
        session.rollback()
        logger.exception("Failed to register repository")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/repos", response_model=RepoListResponse)
async def list_repos() -> RepoListResponse:
    session = get_sync_session()
    try:
        repos = session.query(Repository).order_by(Repository.created_at.desc()).all()
        return RepoListResponse(
            repos=[
                RepoInfo(
                    id=r.id,
                    owner=r.owner,
                    name=r.name,
                    url=r.url,
                    default_branch=r.default_branch,
                    last_indexed_commit=r.last_indexed_commit,
                    indexed_at=r.indexed_at,
                    status=r.status,
                )
                for r in repos
            ]
        )
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
            id=repo.id,
            owner=repo.owner,
            name=repo.name,
            url=repo.url,
            default_branch=repo.default_branch,
            last_indexed_commit=repo.last_indexed_commit,
            indexed_at=repo.indexed_at,
            status=repo.status,
        )
    finally:
        session.close()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = get_sync_session()
    try:
        repo = session.query(Repository).filter(Repository.id == request.repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        if repo.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Repository not ready (status: {repo.status}). Please wait for indexing to complete.",
            )

        # Placeholder — Phase 4 will implement the full LangGraph RAG pipeline
        return ChatResponse(
            answer="RAG pipeline not yet implemented. Coming in Phase 4.",
            confidence="low",
        )
    finally:
        session.close()
