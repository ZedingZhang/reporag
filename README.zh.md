# RepoRAG

[English](README.md) | [中文文档](README.zh.md)

面向 GitHub 仓库的 RAG 智能助手，提供基于源码的证据型回答、代码感知检索与可度量的检索质量。

## 开发状态

Phase 1-4 已完成。可用功能：仓库索引、分块、向量化、混合检索、RAG 管线、引用校验、Streamlit 界面、评估框架。Phase 5（打磨、多仓库、高级 reranker）进行中。

## 核心特性

- **代码感知分块** — Markdown 按标题层级切分，Python 源码按 AST 函数/类切分，保留行号与 commit SHA
- **混合检索** — 向量语义检索 + 关键词全文检索，Reciprocal Rank Fusion 合并排序
- **RAG 管线** — LangGraph 风格工作流：问题分类 → 查询改写 → 混合检索 → 重排序 → 证据检查 → 答案生成 → 引用验证
- **引用验证** — 每条回答附带 GitHub permalink（含文件路径+行号），自动检测虚构引用
- **后台索引** — POST 仓库 URL 后通过 FastAPI BackgroundTasks 异步索引
- **评估框架** — Recall@k、MRR、引用覆盖率、延迟，基于 JSONL 数据集驱动

## 一句话定位

RepoRAG 面向开源项目新贡献者，帮助快速理解项目结构、定位相关源码、追踪 issue/PR 背景，并生成带 GitHub permalink 引用的可信回答。

## 架构

```
用户 → Streamlit UI → FastAPI (BackgroundTasks)
                         ├── POST /api/repos/index → GitHub 抓取 → 分块 → 向量化 → DB
                         └── POST /api/chat → 查询改写 → 混合检索 → 重排序 → LLM → 引用
                              ↑                                                        ↓
                              └──────── PostgreSQL + pgvector（向量 + 全文检索） ─────────┘
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, FastAPI |
| RAG 管线 | LangChain（providers）, LangGraph 模式 |
| 数据库 | PostgreSQL + pgvector |
| 前端 | Streamlit |
| 大模型 | DeepSeek V4（OpenAI-compatible），可替换 |
| Embedding | OpenAI-compatible provider，可替换 |
| 开发工具 | pytest（36 个测试）, ruff, Alembic |

## 快速开始

### 环境要求

- Docker 与 Docker Compose
- DeepSeek API Key（或任意 OpenAI-compatible API）
- GitHub Token（可选，将 API 频率限制从 60 提升至 5000 次/小时）

### 启动

```bash
git clone https://github.com/nebula167/reporag.git
cd reporag

cp .env.example .env
# 编辑 .env 填入 API Key

docker compose up --build
```

容器启动时自动执行数据库 migration。

- FastAPI 文档：http://localhost:8000/docs
- Streamlit 界面：http://localhost:8501

### 索引仓库

通过 API：
```bash
curl -X POST http://localhost:8000/api/repos/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/pallets/click"}'
```

或命令行：
```bash
python scripts/ingest_repo.py --repo https://github.com/pallets/click
```

### 提问

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","question":"命令解析在哪里实现的？","top_k":8}'
```

返回包含 `answer`、`citations`（含 GitHub permalink 和行号）、`retrieved_chunks`、`confidence`。

## 环境变量

详见 `.env.example`，关键变量：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 |
| `GITHUB_TOKEN` | GitHub 个人访问令牌（可选，提升频率限制） |
| `LLM_PROVIDER` | LLM 提供商（`deepseek` 或 `openai_compatible`） |
| `DEEPSEEK_API_KEY` | Chat 模型 API Key |
| `DEEPSEEK_BASE_URL` | Chat 模型 API 地址 |
| `DEEPSEEK_MODEL` | 模型名称（如 `deepseek-v4-pro`） |
| `DEEPSEEK_REASONING_EFFORT` | 可选 reasoning effort（设为空禁用） |
| `EMBEDDING_PROVIDER` | Embedding 提供商 |
| `EMBEDDING_API_KEY` | Embedding API Key |
| `EMBEDDING_MODEL` | Embedding 模型名称 |
| `EMBEDDING_DIMENSIONS` | 向量维度（必须与模型输出一致） |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/repos/index` | 索引 GitHub 仓库（异步后台任务） |
| `POST` | `/api/chat` | 提问，返回带引用的回答 |
| `GET` | `/api/repos` | 列出所有已索引仓库 |
| `GET` | `/api/repos/{id}/status` | 查询仓库索引状态 |

## 评估

```bash
python scripts/evaluate.py --dataset examples/eval_dataset.jsonl
```

对已索引仓库运行评估。指标：Recall@5、MRR、引用覆盖率、平均延迟。

数据集 `examples/eval_dataset.jsonl` 包含针对真实公开仓库的问题，运行前需先索引对应仓库。

## 项目结构

```
app/
  core/          配置、日志、Provider Adapter（LLM + Embedding）
  db/            SQLAlchemy 模型、会话、Alembic migration
  github/        GitHub REST API 客户端、URL 解析
  ingestion/     切片器（Markdown、Python AST、JS/TS）、Embedding 客户端
  retrieval/     向量检索、关键词检索、混合融合、Reranker 接口
  rag/           LangGraph 风格管线、Prompt、引用校验
  api/           FastAPI 路由、Pydantic Schema
streamlit_app/   Streamlit 界面
scripts/         ingest_repo.py、evaluate.py
tests/           36 个 pytest 测试
```

## 简历亮点

> 独立完成 RepoRAG，一个面向 GitHub 仓库的 RAG 助手。实现了代码感知切片、混合检索+RRF 融合、引用校验、LangGraph 风格 RAG 管线编排，以及包含 Recall@k、MRR、引用覆盖率、延迟的离线评估体系。

## Roadmap

- [x] 代码感知分块（Markdown、Python AST、JS/TS）
- [x] 混合检索 + RRF 融合
- [x] 引用校验 + GitHub permalink
- [x] 后台异步索引 API
- [x] RAG 管线（改写 → 检索 → 重排 → 生成 → 校验）
- [x] Streamlit 界面接入 API
- [x] 评估框架接入真实检索器
- [ ] Cross-encoder 重排序（当前使用 identity reranker）
- [ ] 多仓库交叉检索
- [ ] Webhook 增量索引
- [ ] Next.js + shadcn/ui 前端
