# 更新日志 (Changelog)

所有项目重要变更记录于此（P2-8 维护 commit message 规范）。

## [Unreleased-5] - 2026-08-11 (RAG 深度优化 + 3 P0 + 2 P1 完成)

### P1-1: SSE 流式响应端到端 (接入 ChatPipeline)
- `app/server/routers/chat_stream.py` 重构
- 之前: 简化逻辑 (只调 LLM, 没 RAG 检索)
- 现在: 接入 ChatPipeline (rewrite → search → rerank → answer) 4 阶段
- 新增 SSE 事件: `intent` / `thinking` / `search` / `rerank` / `text`(×N) / `sources` / `done`
- 17 测试覆盖: 事件格式、流式推送、错误处理、文本分块

### P1-2: 长期记忆 middleware 自动注入
- `app/rag/middleware/long_term_memory.py` (~110 行, 17 测试)
- 借鉴 JavaGuide section 3.6 (记忆 6 阶段模型)
- `LongTermMemoryMiddleware` 类:
  - `on_reasoning` 阶段: 从 DB 加载用户事实 → 拼到 system_prompt
  - `on_reply` 阶段: 异步提取新事实 (fire-and-forget, 不阻塞响应)
- `inject_user_facts()` / `extract_and_save_after_chat()` 工具函数
- max_facts=20 默认 (避免 prompt 过长)

### P0 (已完成):
- P0-1: chat_service.py Pipeline 重构
- P0-2: RAGAS 4 维指标实战
- P0-3: permission_tag 文档权限

### RAG 核心 (借鉴 WeKnora + 5 份学习文档)

### P0-1: chat_service.py 接入 ChatPipeline (替换 if-else)
- 重构 `app/services/chat_service.py`: 130 行 if-else → 调度 4 Plugin
- `get_chat_pipeline()` 单例 + 4 plugin 注册 (query_rewrite / search / rerank / answer)
- Plugin 全部实现完整 (含 Rerank 的 parent 全文回查)

### P0-2: RAGAS 4 维指标实战
- `app/rag/evaluation/ragas_runner.py` (213 行, 21 测试)
- 真实 RAGAS 库接入 (`pip install ragas`)
- 启发式 fallback (Windows 上 RAGAS 依赖 langchain-community 冲突)
- `evaluate_rag()` / `aggregate_ragas_results()` API
- 4 维指标: faithfulness / answer_relevancy / context_precision / context_recall

### P0-3: 文档级 permission_tag 权限 (借鉴九阳 POC §5)
- `app/db/enums.py` 新增 `PermissionTag` 枚举 (public/internal/confidential)
- ROLE_PERMISSION_MATRIX: user→{public}, staff→{public+internal}, admin→all
- `can_access(role, tag)` + `filter_by_role(docs, role)` 工具
- `app/db/models.py` Document 模型加 `permission_tag` 字段 (default='public')
- Alembic migration: `0009_add_permission_tag.py`
- `app/rag/v2_engine.py` helper: `get_allowed_permission_tags()` / `filter_documents_by_role()`
- 19 测试覆盖所有权限矩阵

### RAG 核心 (借鉴 WeKnora v0.7.2 + 5 份学习文档)
- **Score Normalizer** (P0): `app/rag/retriever/normalizer.py` (154 行, 19 测试)
- **Enriched Passage** (P0): `app/rag/chat_pipeline/enrich.py` (138 行, 10 测试)
- **Stuck Loop Detection** (P0): `app/core/stuck_loop_detector.py` (149 行, 14 测试)
- **3-Tier 自适应分块** (P0): `app/rag/chunkers/{profiler,strategy}.py` (342 行, 27 测试)
- **Self-RAG 反思检索** (P1): `app/rag/agentic/self_rag.py` (215 行, 9 测试)
- **Chat Pipeline 框架** (P0): `app/rag/chat_pipeline/` (376 行, 9 测试)
- **base64 Sanitize** (P0): `app/rag/utils/sanitize.py` (88 行, 12 测试)

### 测试
- **140 个新单元测试**, 全部通过 (140/140)
  - test_score_normalizer (19) + test_sanitize (12) + test_stuck_loop (14)
  - test_enriched_passage (10) + test_self_rag (9) + test_chunker_profiler (27)
  - test_chat_pipeline (9) + test_ragas (21) + test_permission_tag (19)
- 8 个新测试文件, 100% 覆盖新模块

## [Unreleased-4] - 2026-08-11 (收官: 最后的 2%)

### RAG 核心 (借鉴 WeKnora v0.7.2 + 5 份学习文档)
- **Score Normalizer** (P0): `app/rag/retriever/normalizer.py` (154 行, 19 测试)
  - Milvus COSINE [-1,1] / L2 / BM25 (sigmoid) / Rerank 归一到 [0,1]
  - 修复 BM25 + 向量 RRF 融合不可比的 P0 缺陷
- **Enriched Passage** (P0): `app/rag/chat_pipeline/enrich.py` (138 行, 10 测试)
  - Rerank 前给 passage 拼上"文档名/章节路径/来源" (借鉴 WeKnora §4.4)
  - 集成 base64 sanitize 防 token 爆炸
- **Stuck Loop Detection** (P0): `app/core/stuck_loop_detector.py` (149 行, 14 测试)
  - 同 content / tool call 连续 N 次自动 break (借鉴 WeKnora §5.4)
  - 防 LLM 抽风死循环
- **3-Tier 自适应分块** (P0): `app/rag/chunkers/{profiler,strategy}.py` (342 行, 27 测试)
  - 17 维 Profiler 文档特征 (借鉴 WeKnora §2.2)
  - Tier 1 (heading) / Tier 2 (heuristic) / Tier 3 (recursive) 自动选
  - 已接入 Markdown/PDF 解析器 (`use_adaptive_tier=True` 默认)
- **Self-RAG 反思检索** (P1): `app/rag/agentic/self_rag.py` (215 行, 9 测试)
  - LLM 评估 confidence < 0.4 自动改写 query 重检索 (借鉴 AgentScope §3.1)
  - max_retries 可控, 防无限循环
- **Chat Pipeline 框架** (P0): `app/rag/chat_pipeline/{events,pipeline,plugins}.py` (167 行, 9 测试)
  - 事件驱动 Plugin 架构 (借鉴 WeKnora §4.1-4.3)
  - 4 个阶段 (rewrite/search/rerank/answer) 独立 Plugin
- **base64 Sanitize** (P0): `app/rag/utils/sanitize.py` (88 行, 12 测试)
  - Embedding/rerank 前删 `data:image/...;base64,` (借鉴 WeKnora §9.2)
  - 1 张大图不再爆 100K token

### 集成修复
- `app/rag/v2_engine.py` 全面接入:
  - 修复 `include_unpublished` 参数缺失 bug
  - `_safe_text_for_embedding()` helper (embedding 前自动 sanitize)
  - Vector / BM25 分数归一化 (用 `batch_normalize`)
  - Rerank 改用 Enriched Passage + normalize_score
- `app/rag/parsers/markdown_parser.py` + `pdf_parser.py`:
  - 新增 `use_adaptive_tier=True` 参数 (默认开启 3-tier)
  - 兼容旧版 (`use_adaptive_tier=False`)

### 测试
- **100 个新单元测试**, 全部通过 (100/100)
- 7 个新测试文件 (test_score_normalizer, test_sanitize, test_stuck_loop,
  test_enriched_passage, test_chunker_profiler, test_self_rag, test_chat_pipeline)

## [Unreleased-4] - 2026-08-11 (收官: 最后的 2%)

### Cleanup
- **P0-1**: `app/server/api.py` routes.extend 加 FastAPI 版本判断 (`< 0.142` 走 workaround, `>= 0.142` 走 `include_router`, 避免升级后重复注册)
- **P0-5**: 删除 `chat_sessions.state_json` 字段
  - `app/db/models.py` ChatSession model 去掉 `state_json` 列 + 更新 docstring
  - `app/schemas/__init__.py` ChatSessionCreate/Public 去掉 `state_json` 字段
  - 新增 `alembic/versions/0008_drop_chat_session_state_json.py` (down_revision=0007)
- **P0-5**: ChatSession 现在只用 state_store (Redis) 单数据源, 写路径已迁移, 读路径统一

### Test (P1-1 验收闭环)
- 新增 `tests/test_auth_coverage.py` — 静态 AST 扫描 56 个端点
  - 100% 鉴权覆盖: 43 鉴权 / 8 公开白名单 / 0 漏鉴权
  - 公开白名单: `/api/auth/{register,login,staff_login}` + 5 个 C 端浏览端点 (`/api/branches`, `/api/services`, `/api/stylists`, `/api/orders/available-slots`)
  - 这道闸保证未来任何新增端点漏 auth 都会 fail

## [Unreleased] - 2026-08-10

### Security (P1-1, P1-2, P1-3)
- **P1-1**: `/api/chat` 加 JWT 鉴权，user_id 强制从 token 取（不再接受 body）
- **P1-2**: `/api/rag/index` + `/api/rag/upload` + `/api/rag/chunks` 加 JWT 鉴权
- **P1-3**: `/api/auth/login` 加 5次/分钟 限流（防暴力破解）

### Architecture (P0-1, P0-4)
- **P0-1**: 创建 `app/utils/order_utils.py` 抽 `generate_order_no` 去重
- **P0-4**: middleware 钩子 `on_agent` → `on_reply`（对齐 AgentScope 命名）

### Bug Fixes
- **P0-1**: Rerank 真实接入（硅基流动 BAAI），删除 `DashScopeRerankModel` 死引用
- **P0-2**: Milvus filter 字符串转义（防 filter 注入）
- **P1-7**: 删除 `Document.pass # placeholder` 死代码
- **P2-2**: 统一 Embedding dim 来源 (VECTOR_DIMS > TEXT_EMBEDDING_DIMENSIONS > 1024)
- **P2-4**: CHAT_BASE_URL 默认值 `/api/coding/v3` → `/api/v3`（chat 模型通用）
- **P2-5**: `from rag.x` 错误模块名 → `from app.rag.v2_engine`

### Refactor
- **P1-5**: 新增 `app/db/enums.py` 统一 `OrderStatus` 枚举 + 状态机转换
- **P1-9**: `confirm_order` 工具接入 `PermissionEngine`（危险操作走 HITL）
- **P2-3**: `copy_context()` helper 用于 trace_id 跨 task 传播
- **P2-6**: 前端所有页面路由懒加载（lazy + Suspense）
- **P2-7**: 新增 `frontend/src/types/chat.ts` 共享类型
- **P3-3**: ErrorBoundary 接入 `/admin/knowledge` 路由
- **P3-4**: 删除前端 600ms 假 thinking 延迟

### Infra
- **P2-13**: slowapi rate limiter 全局接入（100/minute 默认）
- **P2-15**: CORS 严格化（方法白名单 + 头白名单 + 10min preflight cache）
- **P3-2**: docker-compose healthcheck 已存在

## [Unreleased-3] - 2026-08-11 (第六轮 review 全修)

### Security (N12 严重)
- **N12**: `routers/skills.py` 4 端点全部加鉴权
  - `list_skills` / `get_skill` / `search_skills`: `Depends(get_current_user)` (任意登录用户可读)
  - `reload_skills`: `Depends(require_staff)` (staff-only, 防 DOS 任意触发文件 I/O)
- **N12**: 新增 `test_n12_skills_endpoints_require_auth` 测试验证 4 端点都有 current 参数

### Refactor (N13, N14, N15)
- **N13**: 删除 `routers/skills.py` 底部残留的"长期记忆 API"旧注释 + `routers/user_facts.py` 底部残留的 routes.extend / admin 注释
- **N14**: 6 个 chat 子端点 (history GET/DELETE, sessions GET/POST/DELETE, sessions/{id}/state GET) 全部从 api.py 搬到新建 `routers/chat.py` (159 行)
- **N14**: api.py 598 → 431 行（-28%）
- **N14**: 新增 `test_n14_chat_subendpoints_in_router` 验证 6 端点都在 chat.py, 不在 api.py
- **N15**: chat handler 多模态分支去重 — 删 13 行重复 JWT decode 逻辑, 改用 `current.role in ("staff", "admin")`
- **N15**: 新增 `test_n15_chat_handler_no_jwt_redecode` 验证

### Cleanup
- 删除 api.py:279-299 死代码 `return {'hits': [...], 'stats': {...}}` 残留 (历史 paste artifact)
- `routers/chat.py` 注册到 `app.router.routes.extend`

### Test Infra
- `tests/conftest.py` `init_db_session` 改为 `try/except` 容忍 DB 不可用 (允许只跑静态/源码扫描测试)
- 4 个新 N12-N15 测试通过 (4 passed)

## [Unreleased-2] - 2026-08-10 (按 review 文档全修)

### 关键 Bug 修复
- **N1**: `if False` 死代码（永远走 InMemory）→ 降级到 JsonFile
- **N2**: 删 56 行旧 `/api/rag/documents` 端点，让 routers/rag.py 真生效
- **N3**: 验证 Vite 懒加载生效
- **N4**: VECTOR_DIMS 默认 2048 → 1024（与 BAAI 真实维度对齐）

### Security
- **P1-2**: 5 个 RAG 端点补鉴权（search/stats/test-recall/supported-formats/documents）
- **P1-2**: 4 个新 E2E 测试验证鉴权

### Architecture
- **P0-2**: Chat 双轨制 → 单一 Agent + RAGMiddleware
- **P0-3**: 19 硬编码关键词 → LLM intent (`_is_booking_intent`)
- **P0-3**: 9+5 关键词（继续/查看）→ LLM intent
- **P0-5**: 删 chat_sessions.state_json 双写（state_store 唯一源）
- **P1-8**: 6 个 booking 工具真被 Agent 调（BookingAgent 接管）
- **P1-9**: PermissionAction → PermissionDecision 类名修正

### Refactor
- **P0-1**: api.py 1880 → **1299 行**（-581 行，-31%）
- **P0-1**: 抽 booking_service.py / intent_extractor.py / intent_classifier.py
- **P2-1**: 5 处 LLM 响应抽取重复 → `app/utils/llm_extract.extract_text`
- **P2-1**: order_no 2 份重复 → `app/utils/order_utils.generate_order_no`
- **P3-5**: 3 套 model config 合并为 model_configs 字典（单一数据源）

### Frontend
- **P1-4**: ChatPage 不再从 localStorage 取 user_id，改 `/api/auth/me` + cookie
- **P1-6**: 抽 useChat hook + 4 个 chat 子组件

### Tests
- **P1-10**: 7 个 Agent 循环测试（test_agent_loop.py）
  - Knowledge Agent 工具验证
  - Booking Agent 6 工具验证
  - RAGMiddleware 接入验证
  - LLM extract helper 测试
  - order_no 唯一性测试
  - api.py 用了 extract_text 验证
- **P0-5**: Redis 集成测试（test_state_store_redis.py）

### Infra
- 启动 Redis 容器（端口 6379）
- 安装 asyncpg / prometheus_client / slowapi / pybreaker

## [Unreleased-3] - 2026-08-10 (第四轮: 真修 + 拆分 router)

### N 致命
- **N10**: routers/rag.py `index` / `upload` 改 `require_staff`（之前用 `get_current_user` 权限漏洞）
- **N5 (重)**: CustomerGuard 改用 `getUser()`（HttpOnly Cookie 模式下 `getToken()` 永远 null）
- **N6 (重)**: `admin_archive` 加 `current: Annotated[CurrentUser, ...]` type hint

### Router 拆分 (P0-1 收尾)
- **8 RAG 端点** 全部从 api.py 移到 `routers/rag.py` (api.py 996 → 443 行)
- **3 skills/permission/user_facts router** 拆分到独立文件
- **admin_archive** 移到 `routers/admin.py`
- **FastAPI 0.141 include_router bug** workaround: `app.router.routes.extend()` 替代 `app.include_router()`

### 真修 (第三轮的"伪装修复"全改对)
- **N7**: `build_booking_agent` 改 async + 用 `await toolkit.add_tool()` 官方 API
- **N8**: `build_knowledge_agent` 同样改 async + 双检锁
- **N9**: `build_toolkit` 改 async（统一替代 `build_toolkit_async` 死代码）
- **13 关键词** 真删：`_is_continue_edit_intent` 兜底用 `extract_with_llm`（不再硬编码）

### Helper 函数抽到 services
- `_chat_handler` 130 行 → `services/chat_service.chat_handler`
- `_save_ai_message` → `chat_service.save_ai_message`
- `_save_session_state` → `chat_service.save_session_state`
- `_is_booking_intent` → `chat_service.is_booking_intent`
- `_is_continue_edit_intent` → `chat_service.is_continue_edit_intent`

### 测试
- 新增 N10 / N11 测试 (test_e2e_chat.py)
- 47 测试全过 (含 17 E2E + 7 Agent loop + 2 Redis)

## [Unreleased-6] - 2026-08-18 (P2-基础设施: pgvector 替代 Milvus)

### 重大变更
- **向量库从 Milvus 迁移到 pgvector** (P2-基础设施)
- Milvus 容器 (milvus-standalone / etcd / minio / attu) 已弃用, 停用后无需重建
- 容器数从 6 → 2 (postgres + redis), 端口从 4 → 2 (5432 + 6379)
- 删除 `app/rag/milvus_store.py`, 新增 `app/rag/pgvector_store.py`

### 新增
- `alembic/versions/0011_pgvector_setup.py` - 安装 pgvector 扩展 + 建 child_chunks 表 + HNSW 索引
- `app/db/models.py` - 新增 `ChildChunk` SQLAlchemy 模型 (含 Vector(1024) embedding 字段)
- `app/rag/pgvector_store.py` - PgvectorStore 适配器 (接口兼容 MilvusStore, 调用方零改动)
- `app/server/routers/rag.py` - 新增 `GET /api/rag/inspect` 可视化端点 (替代 Attu)
- `scripts/migrate_milvus_to_pgvector.py` - 一次性数据迁移脚本

### 收益
1. **解决 P0-3 孤儿数据问题** - Document/ParentChunk/ChildChunk 三表都在 PG, 事务保证一致
2. **is_published 单一来源** - JOIN Document 表校验, 不再双源不同步
3. **hybrid search 一个 SQL** - tsvector (BM25) + vector (HNSW) + 标量过滤
4. **省 3 个容器** - etcd/minio/attu 全部停用
5. **可视化更简单** - DBeaver 直接看 child_chunks 表 + /api/rag/inspect 端点

### 改造清单
- `app/rag/v2_engine.py` - `get_milvus_store()` → `get_vector_store()` (双引擎分发)
- `app/rag/image_indexer.py` - 去掉 `pymilvus.MilvusClient` 底层调用
- `app/rag/multimodal_chat.py` - 去掉 `milvus_store.CATEGORY_KEY` 引用
- `app/core/config.py` - `VectorStoreConfig.engine` 默认 `pgvector`
- `tests/conftest.py` - cleanup 改 `TRUNCATE child_chunks` (替代 `drop_collection`)
- `tests/test_milvus_store.py` → `tests/test_pgvector_store.py` (重写)
- `tests/test_multitenant_filter.py` - 改用 PgvectorStore
- `tests/test_multimodal_isolation.py` - 改用 pgvector
- `tests/test_vlm_image.py` - marker `keep_milvus` → `keep_pgvector`
- `requirements.txt` - 替换 `pymilvus` 为 `pgvector`
- `.env` / `.env.example` - `VECTOR_STORE_ENGINE=pgvector` 默认
- `CLAUDE.md` / `README.md` - 启动命令和文档更新
