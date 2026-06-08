from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.routes import router as api_router
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title="RepoRAG",
    description="RAG assistant for understanding GitHub repositories",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
