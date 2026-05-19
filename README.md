# RepoRAG

[中文文档](README.zh.md) | [English](README.md)

RAG assistant for understanding GitHub repositories with source-grounded answers, code-aware retrieval, and measurable retrieval quality.

## Status

Phase 1-4 complete. Working: repo indexing, chunking, embedding, hybrid retrieval, RAG pipeline, citation validation, Streamlit UI, evaluation framework. Phase 5 (polish, multi-repo, advanced reranker) in progress.

## Core Features

- **Code-aware chunking** — chunks Markdown by headings, Python source by AST functions/classes, preserves line numbers and commit SHAs
- **Hybrid retrieval** — combines vector (semantic) and keyword (full-text) search with Reciprocal Rank Fusion
- **RAG pipeline** — LangGraph-inspired workflow: question classification, query rewrite, hybrid retrieval, rerank, evidence check, answer generation, citation validation
- **Citation validation** — every answer includes GitHub permalinks with file paths and line ranges; fabricated citations are detected
- **Background ingestion** — POST a GitHub URL, indexing runs asynchronously via FastAPI BackgroundTasks
- **Evaluation framework** — Recall@k, MRR, citation coverage, latency metrics driven by a JSONL dataset

## Architecture

```
User → Streamlit UI → FastAPI (BackgroundTasks)
                         ├── POST /api/repos/index → GitHub Client → Chunkers → Embedding → DB
                         └── POST /api/chat → Query Rewrite → Hybrid Retrieval → Rerank → LLM → Citations
                              ↑                                                                    ↓
                              └────────── PostgreSQL + pgvector (vector + full-text) ──────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI |
| RAG Pipeline | LangChain (providers), LangGraph pattern |
| Database | PostgreSQL + pgvector |
| Frontend | Streamlit |
| LLM | DeepSeek V4 (OpenAI-compatible), swappable |
| Embeddings | OpenAI-compatible provider, swappable |
| Dev tools | pytest (36 tests), ruff, Alembic |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- DeepSeek API key (or any OpenAI-compatible API)
- GitHub token (optional, raises rate limit from 60 to 5000 req/h)

### Setup

```bash
git clone https://github.com/nebula167/reporag.git
cd reporag

cp .env.example .env
# Edit .env with your API keys

docker compose up --build
```

- FastAPI docs: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501

Migrations run automatically on container start.

### Index a Repository

Via API:
```bash
curl -X POST http://localhost:8000/api/repos/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/pallets/click"}'
```

Or via CLI:
```bash
python scripts/ingest_repo.py --repo https://github.com/pallets/click
```

### Ask Questions

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","question":"Where is command parsing implemented?","top_k":8}'
```

Response includes `answer`, `citations` (with GitHub permalinks and line numbers), `retrieved_chunks`, and `confidence`.

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GITHUB_TOKEN` | GitHub personal access token (optional, raises rate limit) |
| `LLM_PROVIDER` | LLM provider (`deepseek` or `openai_compatible`) |
| `DEEPSEEK_API_KEY` | API key for the chat model |
| `DEEPSEEK_BASE_URL` | Base URL for the chat model API |
| `DEEPSEEK_MODEL` | Model name (e.g., `deepseek-v4-pro`) |
| `DEEPSEEK_REASONING_EFFORT` | Optional reasoning effort (set empty to disable) |
| `EMBEDDING_PROVIDER` | Embedding provider (`openai_compatible`) |
| `EMBEDDING_API_KEY` | API key for embeddings |
| `EMBEDDING_MODEL` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | Embedding vector dimensions (must match model output) |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/repos/index` | Index a GitHub repository (async) |
| `POST` | `/api/chat` | Ask a question, get cited answer |
| `GET` | `/api/repos` | List all indexed repositories |
| `GET` | `/api/repos/{id}/status` | Get repository indexing status |

## Evaluation

```bash
python scripts/evaluate.py --dataset examples/eval_dataset.jsonl
```

Evaluates against indexed repos. Metrics: Recall@5, MRR, Citation Coverage, Avg Latency.

The eval dataset (`examples/eval_dataset.jsonl`) contains real questions for real public repos. Repos must be indexed before running evaluation.

## Project Structure

```
app/
  core/          config, logging, provider adapters (LLM + embedding)
  db/            SQLAlchemy models, session, Alembic migrations
  github/        GitHub REST API client, URL parser
  ingestion/     chunkers (markdown, Python AST, JS/TS), embedding client
  retrieval/     vector search, keyword search, hybrid fusion, reranker interface
  rag/           LangGraph-style pipeline, prompts, citation validation
  api/           FastAPI routes, Pydantic schemas
streamlit_app/   Streamlit UI
scripts/         ingest_repo.py, evaluate.py
tests/           36 pytest tests
```

## Resume Highlight

> Built RepoRAG, a GitHub repository RAG assistant with code-aware chunking, hybrid retrieval, reranking, citation validation, and a LangGraph-inspired answer generation pipeline. Includes evaluation framework with Recall@k, MRR, citation coverage, and latency metrics.

## Roadmap

- [x] Code-aware chunking (Markdown, Python AST, JS/TS)
- [x] Hybrid retrieval with RRF fusion
- [x] Citation validation with GitHub permalinks
- [x] Background ingestion API
- [x] RAG pipeline (query rewrite → retrieve → rerank → generate → validate)
- [x] Streamlit UI connected to API
- [x] Evaluation framework with real retriever
- [ ] Cross-encoder reranker (currently identity reranker)
- [ ] Multi-repo cross-reference
- [ ] Webhook-based re-indexing
- [ ] Next.js + shadcn/ui frontend
