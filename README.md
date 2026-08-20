# 美发智能知识助手 (Hairstylist KB Agent)

> 企业级 RAG + 多模态对话系统。火山方舟 LLM + 硅基流动 Embedding + **pgvector 向量库 (P2)** + PG 关系库。

## 📊 项目状态

- ✅ 测试: 200+ 通过
- ✅ 代码: ~5500 行
- ✅ Stage 1 + Stage 2 全部完成
- ✅ P0 高可用 5/5 (JWT / 熔断 / 幂等 / 归档 / pgvector 验证)

## 🏗️ 架构

```
Client (React/Vite)
   ↓ HTTP
FastAPI (8000)
   ↓ asyncpg
   ├─ PostgreSQL 16
   ├─ pgvector (HNSW, 跟 PG 同实例)
   ├─ Redis (LLM cache)
   └─ External APIs
       ├─ 火山方舟 (ark-code-latest, multimodal)
       └─ 硅基流动 (BAAI text embedding, rerank)
```

## 📋 环境要求

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端 |
| Node.js | 20+ | 前端 |
| PostgreSQL | 16 | 业务库 + BM25 |
| pgvector | 0.5+ | PG 扩展 (向量库) |
| Docker | 24+ | 容器化 |

## 🚀 部署

### 0. 一次性准备

- 安装 **WSL**（Ubuntu 发行版，例如 `Ubuntu-Docker`），里面装 Docker Engine
  （本项目不用 Docker Desktop，因为开发机是 Windows + Git Bash）
- Python 3.11+ 装好，建议用 `.venv`
- Node.js 20+

### ⚡ 手动启动速记（日常 3 窗口）

> **日常开发**只需开 3 个 Git Bash 窗口，每个跑一条：

```bash
# 窗口 1 · 数据库层 (WSL Docker 2 容器: postgres + redis, P2-基础设施)
wsl -d Ubuntu-Docker -- service docker start
sleep 3 && wsl -d Ubuntu-Docker -- docker start hairstylist-postgres hairstylist-redis
```

```bash
# 窗口 2 · 后端 (FastAPI, 端口 8000)
cd e:/hairstylist-kb-agent
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m uvicorn app.server.api:app --host 0.0.0.0 --port 8000
# 验证: curl http://localhost:8000/health  →  {"status":"healthy",...}
```

```bash
# 窗口 3 · 前端 (Vite, 端口 5173)
cd e:/hairstylist-kb-agent/frontend
npm run dev
# 验证: http://localhost:5173 (HTTP 200)
```

启动完访问：
- 前端 http://localhost:5173
- 后端 API 文档 http://localhost:8000/docs
- ~~Attu (Milvus UI) http://localhost:3001~~ (已弃用, 改用 DBeaver + /api/rag/inspect)
- DBeaver: localhost:5432 (PG `hairstylist` / `hair` / `hair123`)

### 1. 启动依赖（WSL Docker 容器）

容器已预建（`docker ps -a` 能看到 2 个：`hairstylist-postgres` / `hairstylist-redis`），日常只需 `start`：

```bash
# 启动 WSL Docker daemon（如已运行可跳过）
wsl -d Ubuntu-Docker -- service docker start
sleep 3

# P2-基础设施: 2 个容器 (postgres + redis), pgvector 跟 PG 同实例
wsl -d Ubuntu-Docker -- docker start hairstylist-postgres hairstylist-redis

# 验证
wsl -d Ubuntu-Docker -- docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# 预期: 5432 / 6379 / 19530 / 3001 都暴露在 0.0.0.0
```

> 端口对照：PG=5432 (含 pgvector) / Redis=6379
> 数据落盘：PG 容器自带 volume，重启不丢数据。
> 全新机器首次部署：用对应的 `docker run` 命令（参考 `docs/INTERVIEW_NOTES.md` MVP-1）建容器再 `start`。

### 2. 后端

```bash
# 装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env
# 编辑 .env: 填 JWT_SECRET (用 openssl rand -base64 32)
# 填 CHAT_API_KEY / EMBEDDING_API_KEY / RERANK_API_KEY

# 初始化数据库（首次或 schema 变化时）
alembic upgrade head
python scripts/init_test_data.py  # 业务数据 (分店 / 发型师 / 服务)

# 启动 (本机用 .venv, Git Bash 必加 PYTHONIOENCODING)
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m uvicorn app.server.api:app --host 0.0.0.0 --port 8000
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
# 代理 /api → http://localhost:8000
```

### 4. 验证

- 后端: `curl http://localhost:8000/health` → `{"status": "healthy"}`
- 前端: `http://localhost:5173` 看登录页
- API 文档: `http://localhost:8000/docs` (Swagger)
- ~~Milvus UI: `http://localhost:3001`（Attu）~~ (已弃用)
- pgvector 可视化: DBeaver `localhost:5432` / `hairstylist` / `child_chunks` 表
- pgvector 可视化: `curl http://localhost:8000/api/rag/inspect?doc_id=xxx`

## 📁 项目结构

```
app/
├── auth/                # JWT 认证
├── core/                # 业务核心
│   ├── config.py        # 配置 (env)
│   ├── model_factory.py # LLM/Embedding 工厂
│   ├── cache/           # LRU + Redis
│   ├── concurrency/     # 分布式锁
│   ├── gateway/         # Model Gateway (熔断+降级)
│   ├── tools/           # Agent 工具
│   ├── archiver.py      # 数据归档
│   ├── metrics.py       # Prometheus 指标
│   └── ...
├── db/                  # SQLAlchemy 模型
├── embedding/           # Embedding 适配器 (ark + siliconflow)
├── rag/                 # RAG 引擎
│   ├── v2_engine.py     # 父子分块 + 检索
│   ├── hybrid/          # BM25 + RRF
│   ├── query/           # 6 策略改写
│   ├── parsers/         # PDF/Word/Excel
│   ├── chunkers/        # 智能分块
│   └── evaluation/      # 评估集
├── safety/              # 敏感词 / HITL
├── schemas/             # Pydantic
└── server/              # FastAPI 入口
    └── routers/          # 业务路由

tests/                   # 单元 + 集成
alembic/                 # DB 迁移
scripts/                 # 工具 (ingest / eval / init)
docs/                    # 设计文档
deploy/                  # Prometheus 配置
frontend/                # React 前端
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn + Pydantic |
| 数据库 | PostgreSQL 16 + SQLAlchemy 2.0 |
| 向量库 | pgvector (PG 扩展, HNSW, 1024 维) |
| 缓存 | Redis (LLM 响应) + LRUCache (本地) |
| Embedding | 火山方舟多模态 + 硅基流动 BAAI |
| LLM | 火山方舟 ark-code-latest |
| 监控 | Prometheus + Grafana |
| 文档解析 | MinerU 2.x |
| 前端 | React 19 + Vite + TypeScript + Tailwind |

## 🔧 故障排查

| 问题 | 解决 |
|------|------|
| `pgvector: dim 1024 vs 2048 mismatch` | 删 child_chunks 表重建 (`TRUNCATE child_chunks`) |
| `ConnectionRefused 8000` | `wsl -d Ubuntu-Docker -- service docker start` 再 start 容器 |
| `JWT secret 不安全` | `openssl rand -base64 32` 重新生成 |
| Alembic `KeyError: '0008'` | 0009 的 `down_revision` 写错了，应该是 `"0008_drop_state_json"` |
| `[object Object]` 错误 | 响应是 array, 前端没序列化 (查 console) |
| Embedding 401 欠费 | 改用硅基流动 (BAAI 免费) |

## 📚 文档

- [docs/MASTER_ROADMAP.md](docs/MASTER_ROADMAP.md) - 完整路线图
- [docs/INTERVIEW_NOTES.md](docs/INTERVIEW_NOTES.md) - 面试话术
- [docs/CI_CD.md](docs/CI_CD.md) - CI/CD 流程
- [docs/FRONTEND_PROMPTS.md](docs/FRONTEND_PROMPTS.md) - 前端 figma 提示词
- [docs/archive/](docs/archive/) - 历史设计文档

## 📜 License

Proprietary - Internal Use Only.
