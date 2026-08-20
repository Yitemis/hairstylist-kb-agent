# CLAUDE.md

> 企业级 RAG + 多模态对话系统 (美发行业 B 端知识助手)

## 原则

1. **借鉴不抄袭** — 所有实现参考 `docs/LONG_TERM_MEMORY_*.md`，写自己的代码。
2. **先规划后执行** — 复杂任务先看 `docs/MASTER_ROADMAP.md` 排优先级。
3. **真实数据测试** — `/e/mineru-output/test_30pages/` 30 页 PDF 已就绪，少用 mock。
4. **借鉴 > 重复造轮子** — Redis/PG (含 pgvector) 等基础设施用现成的；不重新实现。
5. **不硬编码规则** — 业务规则（意图识别/分类/路由）让 LLM 决定，代码只写降级。

## 硬约束（不可违反）

- **不硬编码密钥** — 所有 secret 走 `.env`。
- **不删除 `docs/`** — 这是项目的学习资产。
- **不在代码里写意图规则** — 关键词 fallback 只能在 LLM 失败时用，不能作为主要逻辑。
- **不修改 PG schema 不带 migration** — schema 变更必须配 alembic revision (含 pgvector 扩展 / child_chunks 表)。
- **不破坏多租户隔离** — 所有 RAG 查询必须传 `tenant_id` + `audience_filter`。
- **不写超过 50 行不带测试的代码** — TDD 优先。

## 当前状态

| 资源 | 状态 | 备注 |
|------|------|------|
| PG `hairstylist-postgres` | ✅ 5432 端口 | WSL Docker, 业务库 + pgvector 向量库同实例 |
| Redis `hairstylist-redis` | ✅ 6379 端口 | WSL Docker, 容器已有 |
| ~~Milvus `milvus-standalone`~~ | ❌ 已弃用 | P2-基础设施: 改用 pgvector (无需独立容器) |
| 后端 FastAPI | ✅ 8000 端口 | `uvicorn app.server.api:app` |
| 前端 Vite | ✅ 5173 端口 | `frontend/` 里 `npm run dev` |
| 火山方舟 multimodal | ❌ **欠费停用** | `MM_EMBEDDING_ENABLED=0` |
| 硅基流动 BAAI | ✅ 14 元余额 | text_embedding + rerank |
| 火山方舟 **agent plan** | ✅ **2026-08-20 切换** | `/api/plan/v3` chat OK (原 coding plan 欠费) |
| 真实 PDF (30 页) | ✅ `/e/mineru-output/test_30pages/` | 评估用 |

## 🚀 启动流程（本机 WSL Docker 环境）

> 本机用 WSL `Ubuntu-Docker` 跑 Docker daemon（**不是 Docker Desktop**，那玩意没装）。
> 6 个容器都已建好（`docker ps -a` 能看到），下次开机只需 `start`，不用 `up`。

### 一键启动（整个项目）

```bash
# ===== 1. 数据库层（WSL Docker 容器）=====
wsl -d Ubuntu-Docker -- service docker start
sleep 3
# P2-基础设施: pgvector 跟 PG 同实例, 无需独立容器
wsl -d Ubuntu-Docker -- docker start hairstylist-postgres hairstylist-redis

# 验证: 应该看到 6 个 Up
wsl -d Ubuntu-Docker -- docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# ===== 2. 后端（Git Bash）=====
cd e:/hairstylist-kb-agent
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m uvicorn app.server.api:app --host 0.0.0.0 --port 8000
# 验证: curl http://localhost:8000/health → {"status":"healthy",...}

# ===== 3. 前端（Git Bash，新窗口）=====
cd e:/hairstylist-kb-agent/frontend
npm run dev
# 验证: http://localhost:5173 (HTTP 200)
```

### 第一次初始化（新机部署）

```bash
cd e:/hairstylist-kb-agent

# 1. DB 迁移到 head
./.venv/Scripts/python.exe -m alembic upgrade head

# 2. 业务测试数据（分店/发型师/服务）
./.venv/Scripts/python.exe scripts/init_test_data.py
```

> ⚠️ **历史坑**: `0009` migration 的 `down_revision` 必须是 `"0008_drop_state_json"`，不是 `"0008"`。如果 alembic 报 `KeyError: '0008'`，去 [alembic/versions/0009_add_permission_tag.py](alembic/versions/0009_add_permission_tag.py) 改。

## 🗄️ 数据库连接

### DBeaver (PostgreSQL)

打开 `D:\DBeaver\dbeaver.exe` → 新建连接 → **PostgreSQL**：

| 字段 | 值 |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `hairstylist` |
| Username | `hair` |
| Password | `hair123` |

第一次会弹 **"Download missing driver files"**，点下载。能看到表：`users` / `staffs` / `branches` / `stylists` / `services` / `orders` / `user_facts` / `documents` / `parent_chunks` / `child_chunks` / `pending_actions` 等。

**P2-基础设施: pgvector 跟业务库同实例, 用 DBeaver 看 child_chunks 表即可**。
也可用 `GET /api/rag/inspect` 端点看统计和 chunk 列表 (替代 Attu)。

DBeaver 也能连 Redis（端口 6379，Driver 选 Redis 即可）。

## 常用命令

```bash
# 后端 (Git Bash, 端口 8000)
cd e:/hairstylist-kb-agent
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m uvicorn app.server.api:app --host 0.0.0.0 --port 8000

# 前端
cd e:/hairstylist-kb-agent/frontend && npm run dev

# 测试 (PG)
cd e:/hairstylist-kb-agent
DATABASE_URL="postgresql+asyncpg://hair:hair123@localhost:5432/hairstylist" \
  ./.venv/Scripts/python.exe -m pytest tests/ -v

# 纯单测 (无服务, 30s)
./.venv/Scripts/python.exe -m pytest tests/test_idempotency.py tests/test_jwt_security.py \
       tests/test_model_gateway.py tests/test_model_router.py -v

# DB 迁移
./.venv/Scripts/python.exe -m alembic upgrade head

# 跑 RAG 评估
./.venv/Scripts/python.exe scripts/run_rag_evaluation.py

# 索引 PDF
./.venv/Scripts/python.exe scripts/ingest_mineru_output.py --md <file.md> --doc-id <id> --tenant demo
```

## 关键路径

| 路径 | 作用 |
|------|------|
| `app/rag/v2_engine.py` | RAG 主引擎 (父子分块 + 检索) |
| `app/embedding/router.py` | ModelRouter (5 capability) |
| `app/core/cache/llm_cache.py` | LRU / Redis 双后端 |
| `app/core/concurrency/lock.py` | PG advisory_lock |
| `app/core/archiver.py` | 数据热冷分离 |
| `app/server/api.py` | FastAPI 入口 (注意 `chat` 路由用 `body: dict = None, request: Request = None`) |
| `frontend/.figma/make/site.json` | Figma 设计 tokens |
| `frontend/src/index.css` | CSS 设计 tokens (颜色/字体) |

## 重要约定

- **多租户隔离**：所有 RAG 查询默认 `tenant_id` + `audience_filter=["user", "all"]`。
- **缓存策略**：`REDIS_URL` 存在 → Redis，否则 LRU。`LLM 响应` 1h TTL，`幂等` 24h TTL。
- **降级**：Redis 失败 → LRU；多模态 embedding 失败 → 走纯文本；LLM 失败 → 返回固定消息。
- **JWT**：启动时 fail-fast，secret 需 ≥32 字符 + 2 种字符类。
- **幂等**：高风险操作（订单/支付）必须用 `Idempotency-Key` 头。
- **意图识别**：用 `_detect_intent_with_llm`，兜底用 `cache_get(cache)` (LRU/Redis 兼容)。

## 借鉴来源 (不重复内容)

详细见 `docs/`：
- `docs/MASTER_ROADMAP.md` — **权威路线图** (3 周冲刺计划)
- `docs/JAVAGUIDE_LEARNING.md` — 高可用/性能/分布式设计
- `docs/INTERVIEW_NOTES.md` — 面试话术
- `docs/PROJECT_AUDIT.md` — 12 个 P0/P1/P2 风险
- `docs/LONG_TERM_MEMORY_EKBS_AI_SERVICE.md` — 借鉴 ekbs
- `docs/LONG_TERM_MEMORY_JOYOUNG_POC.md` — 借鉴九阳 POC
- `docs/LONG_TERM_MEMORY_JAVAGUIDE_AI.md` — RAG/Agent 体系
- `docs/CI_CD.md` — CI/CD 流程

## 完成进度 (25+ commit)

- ✅ **Stage 1** (6/6): PG/MinerU/Alembic/父子分块/pgvector
- ✅ **Stage 2** (7/7): BM25/6策略/HITL/记忆/SSE/Prometheus/VLM
- ✅ **P0 高可用** (5/5): JWT/熔断/订单幂等/归档/pgvector 验证
- ✅ **工程实践**: Redis 缓存 / CI/CD / RAG 评估 / Context Compression / 分布式锁 / 多模态 / RBAC
- ⏳ **P1 待做**: RAG 3 层校验 / Knowledge 增量更新
- ⏳ **P2 待做**: 数据脱敏 / 分布式事务 outbox / 雪花 ID / K8s

## 注意事项

- 火山方舟 multimodal 欠费 → 多模态图片功能不可用，等充值。
- conftest.py 用了 `NullPool` + `SelectorEventLoopPolicy` (Windows + asyncpg 跨 loop 兼容)。
- 启动前检查 PG/Redis 是否运行：`netstat -ano | grep -E ":5432|:6379"`。
- `.env` 改了要重启后端（uvicorn 不在 reload 模式）。
