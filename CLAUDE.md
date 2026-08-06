# CLAUDE.md

> 企业级 RAG + 多模态对话系统 (美发行业 B 端知识助手)

## 原则

1. **借鉴不抄袭** — 所有实现参考 `docs/LONG_TERM_MEMORY_*.md`，写自己的代码。
2. **先规划后执行** — 复杂任务先看 `docs/MASTER_ROADMAP.md` 排优先级。
3. **真实数据测试** — `/e/mineru-output/test_30pages/` 30 页 PDF 已就绪，少用 mock。
4. **借鉴 > 重复造轮子** — Redis/Milvus/PG 等基础设施用现成的；不重新实现。
5. **不硬编码规则** — 业务规则（意图识别/分类/路由）让 LLM 决定，代码只写降级。

## 硬约束（不可违反）

- **不硬编码密钥** — 所有 secret 走 `.env`。
- **不删除 `docs/`** — 这是项目的学习资产。
- **不在代码里写意图规则** — 关键词 fallback 只能在 LLM 失败时用，不能作为主要逻辑。
- **不修改 Milvus schema 不带 migration** — schema 变更必须配 alembic revision。
- **不破坏多租户隔离** — 所有 RAG 查询必须传 `tenant_id` + `audience_filter`。
- **不写超过 50 行不带测试的代码** — TDD 优先。

## 当前状态

| 资源 | 状态 | 备注 |
|------|------|------|
| PG `hairstylist-postgres` | ✅ 5432 端口 | 测试用 |
| Milvus `milvus-standalone` | ✅ 19530 端口 | 已配 WSL |
| Redis | ❌ 未启动 | `docker-compose up -d redis` |
| 火山方舟 multimodal | ❌ **欠费停用** | `MM_EMBEDDING_ENABLED=0` |
| 硅基流动 BAAI | ✅ 14 元余额 | text_embedding + rerank |
| 火山方舟 coding plan | ✅ chat OK | |
| 真实 PDF (30 页) | ✅ `/e/mineru-output/test_30pages/` | 评估用 |

## 常用命令

```bash
# 后端
uvicorn app.server.api:app --host 0.0.0.0 --port 8001

# 前端
cd frontend && npm run dev

# 测试 (PG)
DATABASE_URL="postgresql+asyncpg://hair:hair123@localhost:5432/hairstylist" \
  pytest tests/ -v

# 纯单测 (无服务, 30s)
pytest tests/test_idempotency.py tests/test_jwt_security.py \
       tests/test_model_gateway.py tests/test_model_router.py -v

# DB 迁移
alembic upgrade head

# 跑 RAG 评估
python scripts/run_rag_evaluation.py

# 索引 PDF
python scripts/ingest_mineru_output.py --md <file.md> --doc-id <id> --tenant demo
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

- ✅ **Stage 1** (6/6): PG/Milvus/MinerU/Alembic/父子分块
- ✅ **Stage 2** (7/7): BM25/6策略/HITL/记忆/SSE/Prometheus/VLM
- ✅ **P0 高可用** (5/5): JWT/熔断/订单幂等/归档/Milvus 验证
- ✅ **工程实践**: Redis 缓存 / CI/CD / RAG 评估 / Context Compression / 分布式锁 / 多模态 / RBAC
- ⏳ **P1 待做**: RAG 3 层校验 / Knowledge 增量更新
- ⏳ **P2 待做**: 数据脱敏 / 分布式事务 outbox / 雪花 ID / K8s

## 注意事项

- 火山方舟 multimodal 欠费 → 多模态图片功能不可用，等充值。
- conftest.py 用了 `NullPool` + `SelectorEventLoopPolicy` (Windows + asyncpg 跨 loop 兼容)。
- 启动前检查 PG/Milvus 是否运行：`netstat -ano | grep -E ":5432|:19530"`。
- `.env` 改了要重启后端（uvicorn 不在 reload 模式）。
