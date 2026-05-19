# RepoRAG

RAG assistant for understanding GitHub repositories with source-grounded answers, code-aware retrieval, and measurable retrieval quality.

## Core Features

- **Code-aware chunking** — chunks Markdown by headings, Python source by AST functions/classes, preserves line numbers and commit SHAs
- **Hybrid retrieval** — combines vector (semantic) and keyword (exact match) search with Reciprocal Rank Fusion
- **Reranking** — cross-encoder ready re-ranking of retrieval results
- **Citation validation** — every answer includes GitHub permalinks with file paths and line ranges
- **Evaluation framework** — Recall@k, MRR, citation coverage, and latency metrics
- **LangGraph RAG workflow** — query normalization, rewrite, hybrid retrieval, rerank, evidence check, generation, citation validation

## Architecture

```
User → Streamlit UI → FastAPI → LangGraph RAG Pipeline
                                   ├── GitHub Client (repo fetching)
                                   ├── Ingestion (chunking + embedding)
                                   ├── Hybrid Retrieval (vector + keyword)
                                   └── PostgreSQL + pgvector
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI |
| RAG Pipeline | LangChain, LangGraph |
| Database | PostgreSQL + pgvector |
| Frontend | Streamlit |
| LLM | DeepSeek V4 (OpenAI-compatible) |
| Embeddings | OpenAI-compatible provider |
| Dev tools | pytest, ruff, Alembic |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- DeepSeek API key (or any OpenAI-compatible API)

### Setup

```bash
# Clone and enter the project
cd reporag

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker compose up --build
```

- FastAPI docs: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501

### Index a Repository

```bash
python scripts/ingest_repo.py --repo https://github.com/pallets/click
```

### Ask Questions

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","question":"Where is command parsing implemented?","top_k":8}'
```

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GITHUB_TOKEN` | GitHub personal access token (optional, raises rate limit) |
| `LLM_PROVIDER` | LLM provider name (`deepseek`, `openai_compatible`) |
| `DEEPSEEK_API_KEY` | API key for the chat model |
| `DEEPSEEK_BASE_URL` | Base URL for the chat model API |
| `DEEPSEEK_MODEL` | Model name (e.g., `deepseek-v4-pro`) |
| `EMBEDDING_PROVIDER` | Embedding provider (`openai_compatible`) |
| `EMBEDDING_API_KEY` | API key for embeddings |
| `EMBEDDING_MODEL` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | Embedding vector dimensions |

## API

### `POST /api/repos/index`

Trigger indexing for a GitHub repository.

### `POST /api/chat`

Ask a question about an indexed repository.

### `GET /api/repos`

List all indexed repositories.

### `GET /api/repos/{repo_id}/status`

Get indexing status for a repository.

## Evaluation

```bash
python scripts/evaluate.py --dataset examples/eval_dataset.jsonl
```

Metrics: Recall@5, MRR, Citation Coverage, Latency.

## Resume Highlight

> Built RepoRAG, a GitHub repository RAG assistant with code-aware chunking, hybrid retrieval, reranking, citation validation, and LangGraph-based answer generation. Evaluated retrieval quality with Recall@k, MRR, citation coverage, latency, and faithfulness-oriented metrics.

## Roadmap

- [x] Code-aware chunking (Markdown, Python AST, JS/TS)
- [x] Hybrid retrieval with RRF fusion
- [x] Citation validation with GitHub permalinks
- [ ] Multi-repo cross-reference
- [ ] Real-time webhook-based re-indexing
- [ ] Next.js + shadcn/ui frontend
- [ ] Fine-tuned embedding model for code
