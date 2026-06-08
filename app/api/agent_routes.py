from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.providers import get_chat_provider
from app.db.models import Repository
from app.db.session import get_sync_session
from app.ingestion.embeddings import EmbeddingClient
from app.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class CreateAgentRunRequest(BaseModel):
    repo_id: str
    task: str = Field(..., min_length=1)
    mode: str = Field("plan_only", pattern=r"^(plan_only|propose_patch|execute_after_approval)$")
    top_k: int = Field(8, ge=1, le=50)


class CreateAgentRunResponse(BaseModel):
    run_id: str
    status: str


class AgentStepResponse(BaseModel):
    step_id: str
    step_index: int
    node_name: str
    tool_name: str | None = None
    status: str
    latency_ms: int | None = None
    input: dict | None = None
    output: dict | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    repo_id: str | None = None
    task: str
    mode: str
    status: str
    plan: dict | None = None
    result: dict | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    steps: list[AgentStepResponse] = []


class CancelRunResponse(BaseModel):
    run_id: str
    status: str


@router.post("/runs", response_model=CreateAgentRunResponse)
async def create_agent_run(request: CreateAgentRunRequest) -> CreateAgentRunResponse:
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

        from app.agent.service import AgentService
        chat = get_chat_provider()
        ec = EmbeddingClient()
        retriever = HybridRetriever(session, ec)
        svc = AgentService(session, chat, retriever)

        run_id = svc.create_run(
            repo_id=request.repo_id, task=request.task,
            mode=request.mode, top_k=request.top_k,
        )

        return CreateAgentRunResponse(run_id=run_id, status="running")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent run creation failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: str) -> AgentRunResponse:
    session = get_sync_session()
    try:
        from app.agent.service import AgentService
        svc = AgentService(session, None, None)
        data = svc.get_run(run_id)
        if not data:
            raise HTTPException(status_code=404, detail="Agent run not found")
        return AgentRunResponse(**data)
    except HTTPException:
        raise
    finally:
        session.close()


@router.get("/runs/{run_id}/steps")
async def list_agent_steps(run_id: str) -> list[AgentStepResponse]:
    session = get_sync_session()
    try:
        from app.agent.service import AgentService
        svc = AgentService(session, None, None)
        steps = svc.get_steps(run_id)
        return [AgentStepResponse(**s) for s in steps]
    finally:
        session.close()


class ResolveApprovalRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(approved|rejected)$")
    comment: str = ""


class ResolveApprovalResponse(BaseModel):
    approval_id: str
    run_id: str
    status: str
    review_comment: str | None = None


@router.post("/approvals/{approval_id}/resolve", response_model=ResolveApprovalResponse)
async def resolve_approval(
    approval_id: str, request: ResolveApprovalRequest,
) -> ResolveApprovalResponse:
    session = get_sync_session()
    try:
        from app.agent.service import AgentService
        svc = AgentService(session)
        result = svc.resolve_approval(
            approval_id, request.decision, request.comment,
        )
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Approval not found or already resolved",
            )
        return ResolveApprovalResponse(**result)
    except HTTPException:
        raise
    finally:
        session.close()


class ContinueRunResponse(BaseModel):
    run_id: str
    status: str
    result: dict | None = None


@router.post("/runs/{run_id}/continue", response_model=ContinueRunResponse)
async def continue_agent_run(run_id: str) -> ContinueRunResponse:
    session = get_sync_session()
    try:
        from app.agent.service import AgentService
        from app.core.providers import get_chat_provider
        from app.ingestion.embeddings import EmbeddingClient
        from app.retrieval.hybrid import HybridRetriever

        chat = get_chat_provider()
        ec = EmbeddingClient()
        retriever = HybridRetriever(session, ec)
        svc = AgentService(session, chat, retriever)

        data = svc.continue_after_approval(run_id)
        if not data:
            raise HTTPException(status_code=404, detail="Run not found")
        if "error" in data:
            raise HTTPException(status_code=400, detail=data["error"])
        return ContinueRunResponse(
            run_id=run_id, status=data["status"], result=data.get("result"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Continue run failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
async def cancel_agent_run(run_id: str) -> CancelRunResponse:
    session = get_sync_session()
    try:
        from app.agent.service import AgentService
        svc = AgentService(session, None, None)
        ok = svc.cancel_run(run_id)
        if not ok:
            raise HTTPException(
                status_code=400, detail="Run cannot be cancelled (invalid state)",
            )
        return CancelRunResponse(run_id=run_id, status="cancelled")
    except HTTPException:
        raise
    finally:
        session.close()
