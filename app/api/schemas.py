from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IndexRepoRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")
    branch: str | None = Field(None, description="Branch to index, defaults to default branch")
    include_issues: bool = Field(True)
    include_pull_requests: bool = Field(True)
    max_issues: int = Field(30, ge=1, le=100)
    max_pull_requests: int = Field(30, ge=1, le=100)


class IndexRepoResponse(BaseModel):
    repo_id: str
    status: str
    message: str


class ChatRequest(BaseModel):
    repo_id: str = Field(..., description="Repository ID")
    question: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=50)


class Citation(BaseModel):
    title: str
    url: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    path: str | None = None
    chunk_type: str | None = None
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    retrieved_chunks: list[RetrievedChunk] = []
    confidence: str = "low"


class RepoInfo(BaseModel):
    id: str
    owner: str
    name: str
    url: str
    default_branch: str | None = None
    last_indexed_commit: str | None = None
    indexed_at: datetime | None = None
    status: str


class RepoListResponse(BaseModel):
    repos: list[RepoInfo]
