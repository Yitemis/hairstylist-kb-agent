<div align="center">

# 美发智能知识助手 (Hairstylist KB Agent)

**企业级 RAG + 多智能体 知识助手 (面向美发行业 B 端)**

</div>

<div align="center">

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org)
[![pgvector](https://img.shields.io/badge/pgvector-0.5+-336791.svg)](https://github.com/pgvector/pgvector)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](#license)

[功能特性](#-功能特性) - [截图 / 演示](#-截图--演示) - [快速开始](#-快速开始) - [配置](#-配置) - [目录说明](#-目录说明)

</div>

---

## 简介

本项目是面向美发行业 B 端商家的智能知识助手, 旨在让发型师在面对客户提问时, 能快速从专业知识库中获取答案.

典型场景:
- "洗头应该用多少度的水温"
- "某款染膏应该怎么调配"
- "烫发的化学原理是什么"
- "客户是否对某成分过敏"

它是一个 **RAG (检索增强生成) + 多智能体** 系统, 集成:
- 从专业理发手册自动构建的知识库
- 多个专精 Agent (知识问答 / 预约 / 业务管理)
- 流式答案 + 引用标注
- 全链路决策日志

---

## 功能特性

| | |
|---|---|
| **混合检索** | 向量 (pgvector HNSW) + BM25 (PG tsvector) + RRF 融合 + BGE Rerank |
| **多智能体** | 知识问答 + 预约 (8 工具) + 业务管理 + 意图分类 |
| **插件式 Pipeline** | 10 个按 priority 串联的插件 (Intake -> Rewrite -> Prefilter -> Recall -> Rerank -> Gate -> Compress -> Generate -> Validate -> Observe) |
| **质量门** | 3 层 Gate + Self-RAG retry |
| **全链路可观测** | decision_log 表 (29 字段, 8 索引) + 5 维 Prometheus 指标 |
| **知识更新** | content_hash 去重 + 软删 + 版本追踪 + IndexAlias 蓝绿切换 |
| **LLM 缓存** | Redis 后端, 重复 query 直接返回, 不调 LLM |
| **生产级** | JWT 鉴权 + 幂等 + 限流 + 熔断 + RBAC 工具权限 |
| **流式输出** | SSE (Server-Sent Events) 实时返回 |

---

## 调用

```bash
# 流式调用示例
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"洗头水温多少度合适?","session_id":"demo"}'

# 返回 SSE 事件流:
# event: meta    -> trace_id, intent, gate_decision, top1_score
# event: chunk   -> "38-40 度左右"
# event: chunk   -> "根据发质调整"
# event: sources -> [{document_id, content, score}]
# event: done    -> latency_ms, phase_latencies
```

---

## 快速开始

### 环境要求

| 组件 | 版本 | 用途 |
|---|---|---|
| Python | 3.11+ | 后端运行时 |
| PostgreSQL | 16+ | 业务库 + 向量库 (含 pgvector 扩展) |
| pgvector | 0.5+ | 向量检索扩展 (PG 16 自带) |
| Redis | 7+ | LLM 缓存 + 长期记忆 |
| Node.js | 20+ | 前端 (可选) |
| Docker | 24+ | 容器化部署 (可选) |

### 安装

#### 方式 A: Docker Compose (推荐, 1 条命令)

```bash
# 1. 克隆
git clone https://github.com/Yitemis/hairstylist-kb-agent.git
cd hairstylist-kb-agent

# 2. 配置
cp .env.example .env
# 编辑 .env: 设置 JWT_SECRET (openssl rand -base64 32), CHAT_API_KEY, EMBEDDING_API_KEY

# 3. 一键启动
docker-compose up -d
# -> API:    http://localhost:8000
# -> Docs:   http://localhost:8000/docs
# -> Metrics: http://localhost:9090

# 4. 初始化 DB
docker-compose exec api alembic upgrade head
docker-compose exec api python scripts/init_test_data.py

# 5. 健康检查
curl http://localhost:8000/health
```

#### 方式 B: 本地开发 (无 Docker)

```bash
# 1. Python 环境
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 启 PG + Redis
docker-compose up -d postgres redis

# 3. 配置
cp .env.example .env
# 编辑 .env, 填入 API key

# 4. 初始化 DB
alembic upgrade head
python scripts/init_test_data.py

# 5. 启后端
PYTHONIOENCODING=utf-8 python -m uvicorn app.server.api:app --host 0.0.0.0 --port 8000

# 6. (可选) 启前端
cd frontend
npm install
npm run dev
# -> http://localhost:5173
```

### 使用

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 同步调用 chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"染发前要做什么测试?","session_id":"test"}'

# 3. SSE 流式调用 (实时返回)
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"烫发的原理是什么?","session_id":"stream1"}'

# 4. 登录 (拿 JWT)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"18800000001","password":"password123"}'

# 5. 跑 RAG 评估
python scripts/run_rag_evaluation.py en      # baseline v1
python scripts/run_rag_evaluation_v2.py en   # Plugin Pipeline v2
```

---

## 配置

所有配置通过 `.env` 环境变量:

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | PostgreSQL + pgvector 连接串 |
| `REDIS_URL` | Redis 缓存 + 长期记忆 |
| `CHAT_*` | LLM 调用相关 (base_url, api_key, model) |
| `TEXT_EMBEDDING_*` | Embedding 模型 (base_url, model, dimensions) |
| `RERANK_*` | Rerank 模型 (base_url, model) |
| `JWT_SECRET` | 鉴权密钥 (用 `openssl rand -base64 32` 生成) |
| `DEFAULT_TENANT_ID` | RAG 默认租户 |
| `LLM_CACHE_SIZE` / `LLM_CACHE_TTL` | LLM 缓存配置 |
| `RATE_LIMIT` | 每分钟限流数 |

完整字段见 [.env.example](.env.example) (含注释). **不要把真实 `.env` 提交到 git** (已在 `.gitignore`).

---

## 目录说明

```
hairstylist-kb-agent/
|-- agents/          # Agent 定义 (knowledge/booking/business/intent)
|-- tools/           # 工具注册 + 权限 + 审计 + 业务/订单工具
|-- memory/          # 长期记忆 LTM + 中间件
|-- prompts/         # 系统提示词模板
|-- skills/          # Harness v2 流程 skill 库 (8 RAG + 4 诊断)
|-- app/             # FastAPI 服务层
|   |-- server/      # 入口 + 路由
|   |-- services/    # 业务逻辑
|   |-- db/          # SQLAlchemy 模型
|   |-- rag/         # RAG 子系统
|   |-- auth/        # JWT
|   +-- core/        # 跨切关注
|-- alembic/         # DB migration
|-- scripts/         # 一次性脚本 (ingest / eval / init)
|-- tests/           # 200+ 单元 + 集成测试
|-- frontend/        # React + Vite (可选管理 UI)
|-- ops/             # Prometheus + Grafana 配置
|-- ARCHITECTURE.md  # Plugin Pipeline 设计
|-- docker-compose.yml
|-- data/            # 运行时数据 (.gitignore)
+-- docs/            # 内部设计文档 (.gitignore)
```

| 目录 | 说明 |
|---|---|
| **agents/** | 多智能体定义: 知识问答 / 预约 / 业务管理 / 意图分类 |
| **tools/** | 工具注册中心 + 权限分级 + 审计 + 业务/订单工具实现 |
| **memory/** | 长期记忆 (LTM) + chat handler 集成中间件 |
| **prompts/** | 系统提示词模板集中管理 (markdown) |
| **skills/** | Harness v2 流程 skill 库 (8 RAG 优化 + 4 诊断) |
| **app/** | FastAPI 服务: 路由 / 业务 / DB / RAG / 鉴权 / 核心配置 |
| **alembic/** | DB migration 脚本 |
| **scripts/** | 运维脚本: PDF 导入, 跑评估, 种子数据 |
| **tests/** | 200+ 测试 (单元 + 集成) |
| **frontend/** | React 19 + Vite 管理 UI (可选) |
| **ops/** | Prometheus + Grafana 监控配置 |
| **data/** | 运行时数据 (agent state, 上传) - .gitignore |
| **docs/** | 内部设计文档 - .gitignore |

Plugin Pipeline 详细设计见 [ARCHITECTURE.md](ARCHITECTURE.md).

---

## License

Proprietary - Internal Use Only.

Copyright (c) 2024-2026 Yitemis. All rights reserved.

---

## Acknowledgments

- [AgentScope 2.0](https://github.com/modelscope/agentscope) - 多智能体框架
- [BGE](https://github.com/FlagOpen/FlagEmbedding) - Embedding + Rerank 模型
- [pgvector](https://github.com/pgvector/pgvector) - Postgres 向量扩展
- [JavaGuide](https://javaguide.cn) - 工程实践参考
- [MinerU](https://github.com/opendatalab/MinerU) - PDF 文档解析
