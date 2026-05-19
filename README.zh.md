# RepoRAG

[English](README.md) | [中文文档](README.zh.md)

面向 GitHub 仓库的 RAG 智能助手，提供基于源码的证据型回答、代码感知检索与可度量的检索质量。

## 核心特性

- **代码感知分块** — Markdown 按标题层级切分，Python 源码按 AST 函数/类切分，保留行号与 commit SHA
- **混合检索** — 向量语义检索 + 关键词全文检索，通过 Reciprocal Rank Fusion 合并排序
- **重排序** — 预留 cross-encoder 接口，支持检索结果二次排序
- **引用验证** — 每条回答附带 GitHub permalink，包含文件路径与行号范围
- **评估框架** — Recall@k、MRR、引用覆盖率、延迟等指标
- **LangGraph RAG 工作流** — 问题规范化 → 查询改写 → 混合检索 → 重排序 → 证据检查 → 答案生成 → 引用验证

## 一句话定位

RepoRAG 面向开源项目新贡献者，帮助用户快速理解项目结构、定位相关源码、追踪 issue/PR 背景，并生成带 GitHub permalink 引用的可信回答。

## 架构

```
用户 → Streamlit UI → FastAPI → LangGraph RAG Pipeline
                                   ├── GitHub Client（仓库抓取）
                                   ├── Ingestion（分块 + 向量化）
                                   ├── Hybrid Retrieval（向量 + 关键词）
                                   └── PostgreSQL + pgvector
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, FastAPI |
| RAG 管线 | LangChain, LangGraph |
| 数据库 | PostgreSQL + pgvector |
| 前端 | Streamlit |
| 大模型 | DeepSeek V4（OpenAI-compatible） |
| Embedding | OpenAI-compatible provider |
| 开发工具 | pytest, ruff, Alembic |

## 快速开始

### 环境要求

- Docker 与 Docker Compose
- DeepSeek API Key（或任意 OpenAI-compatible API）

### 启动

```bash
# 进入项目目录
cd reporag

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 启动全部服务
docker compose up --build
```

- FastAPI 文档：http://localhost:8000/docs
- Streamlit 界面：http://localhost:8501

### 索引仓库

```bash
python scripts/ingest_repo.py --repo https://github.com/pallets/click
```

### 提问

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"<repo_id>","question":"Where is command parsing implemented?","top_k":8}'
```

## 环境变量

详见 `.env.example`，关键变量：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串 |
| `GITHUB_TOKEN` | GitHub 个人访问令牌（可选，提升 API 频率限制） |
| `LLM_PROVIDER` | LLM 提供商（`deepseek`、`openai_compatible`） |
| `DEEPSEEK_API_KEY` | Chat 模型 API Key |
| `DEEPSEEK_BASE_URL` | Chat 模型 API 地址 |
| `DEEPSEEK_MODEL` | 模型名称（如 `deepseek-v4-pro`） |
| `EMBEDDING_PROVIDER` | Embedding 提供商（`openai_compatible`） |
| `EMBEDDING_API_KEY` | Embedding API Key |
| `EMBEDDING_MODEL` | Embedding 模型名称 |
| `EMBEDDING_DIMENSIONS` | Embedding 向量维度 |

## API

### `POST /api/repos/index`

触发 GitHub 仓库索引。

### `POST /api/chat`

对已索引仓库提问。

### `GET /api/repos`

列出所有已索引仓库。

### `GET /api/repos/{repo_id}/status`

查询仓库索引状态。

## 评估

```bash
python scripts/evaluate.py --dataset examples/eval_dataset.jsonl
```

指标：Recall@5、MRR、引用覆盖率、端到端延迟。

## 简历亮点

> 独立完成 RepoRAG，一个面向 GitHub 仓库的 RAG 助手。实现了代码感知切片、混合检索（向量+关键词+RRF融合）、引用校验、LangGraph RAG 工作流编排，以及包含 Recall@k、MRR、引用覆盖率、延迟等多维度的离线评估体系。

## Roadmap

- [x] 代码感知分块（Markdown、Python AST、JS/TS）
- [x] 混合检索 + RRF 融合
- [x] 引用校验 + GitHub permalink
- [ ] 多仓库交叉检索
- [ ] Webhook 实时增量索引
- [ ] Next.js + shadcn/ui 前端升级
- [ ] 代码领域微调 Embedding 模型
