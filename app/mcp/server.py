"""RepoRAG MCP Server.

Exposes RepoRAG tools to Claude Code or any MCP-compatible client.

Start:
    python -m app.mcp.server

Requires: pip install mcp (Python >=3.10)

Environment:
    DATABASE_URL — PostgreSQL connection string
    GITHUB_TOKEN — optional, raises API rate limit
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
"""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger(__name__)


def _get_session():
    from app.db.session import get_sync_session
    return get_sync_session()


def _get_retriever(session):
    from app.ingestion.embeddings import EmbeddingClient
    from app.retrieval.hybrid import HybridRetriever
    return HybridRetriever(session, EmbeddingClient())


def _get_agent_svc(session):
    from app.agent.service import AgentService
    from app.core.providers import get_chat_provider
    from app.ingestion.embeddings import EmbeddingClient
    from app.retrieval.hybrid import HybridRetriever
    chat = get_chat_provider()
    retriever = HybridRetriever(session, EmbeddingClient())
    return AgentService(session, chat, retriever)


def search_code_tool(repo_id: str, query: str, top_k: int = 8) -> str:
    session = _get_session()
    try:
        retriever = _get_retriever(session)
        chunks = retriever.retrieve(query=query, repo_id=repo_id, top_k=top_k)
        results = []
        for c in chunks:
            results.append({
                "path": c.path,
                "chunk_type": c.chunk_type,
                "content": c.content[:800],
                "github_url": c.github_url,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "score": round(c.score, 4),
            })
        return json.dumps({"results": results, "total": len(results)}, indent=2)
    finally:
        session.close()


def create_agent_run_tool(repo_id: str, task: str, mode: str = "plan_only") -> str:
    session = _get_session()
    try:
        svc = _get_agent_svc(session)
        run_id = svc.create_run(repo_id=repo_id, task=task, mode=mode)
        return json.dumps({"run_id": run_id, "status": "created"}, indent=2)
    finally:
        session.close()


def get_agent_run_tool(run_id: str) -> str:
    session = _get_session()
    try:
        svc = _get_agent_svc(session)
        data = svc.get_run(run_id)
        if not data:
            return json.dumps({"error": "Run not found"})
        return json.dumps(data, indent=2, default=str)
    finally:
        session.close()


def resolve_approval_tool(approval_id: str, decision: str, comment: str = "") -> str:
    session = _get_session()
    try:
        svc = _get_agent_svc(session)
        result = svc.resolve_approval(approval_id, decision, comment)
        if not result:
            return json.dumps({"error": "Approval not found or already resolved"})
        return json.dumps(result, indent=2)
    finally:
        session.close()


def _build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "MCP SDK not installed. Run: pip install mcp (requires Python >=3.10)",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp = FastMCP("RepoRAG")

    mcp.tool()(search_code_tool)
    mcp.tool()(create_agent_run_tool)
    mcp.tool()(get_agent_run_tool)
    mcp.tool()(resolve_approval_tool)

    return mcp


def main():
    from app.core.logging import setup_logging
    setup_logging()
    mcp = _build_server()
    mcp.run()


if __name__ == "__main__":
    main()
