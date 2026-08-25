# 项目结构 (2026-08-24 重构)

按标准 agent 开发流程对齐: agents / skills / tools / memory / prompts / tests.

## 顶层目录

按标准 agent 项目结构 (agents / skills / tools / memory / prompts / tests) 对齐.
FastAPI 服务层 (app/) 和项目特定目录 (frontend / data / docs / scripts) 在顶层共存.

```
hairstylist-kb-agent/
|-- agents/         # Agent 定义 (knowledge/booking/business/intent)
|-- app/            # FastAPI 服务层 (server/services/db/rag/auth/core + tests + db/migrations/)
|-- data/           # 运行时数据 (.gitignore)
|-- docs/           # 业务文档 (.gitignore)
|-- frontend/       # 前端 (Vue)
|-- memory/         # 长期记忆 (LTM) + 中间件
|-- prompts/        # 系统提示词模板
|-- scripts/        # 一次性脚本 (ingest / eval)
|-- skills/         # Harness v2 流程 skill 库 (8 RAG + 4 诊断)
|-- tests/          # 单元 + 集成测试 (200+)
+-- tools/          # 工具集 (registry / permission / audit / business / order)
```

| 顶层目录 | 说明 |
|---|---|
| **agents/** | Agent 定义: 知识问答 / 预约 / 业务管理 / 意图分类 |
| **skills/** | 流程 skill 库 (Harness v2, 8 RAG 优化 + 4 诊断) |
| **tools/** | 工具集: 注册中心 / 权限 / 审计 / 业务 / 订单 |
| **memory/** | 长期记忆 (LTM) + 中间件 |
| **prompts/** | 系统提示词模板集中管理 |
| **tests/** | 单元 + 集成测试 (200+) |
| **app/** | FastAPI 服务层 (含 tests/ + db/migrations/ 内嵌) |
| **frontend/** | Vue 前端 (可选) |
| **scripts/** | 一次性脚本 (ingest / eval) |
| **data/** | 运行时数据 (.gitignore) |
| **docs/** | 业务文档 (.gitignore) |

## agents/ - 业务 Agent

| 文件 | 作用 |
|---|---|
| base.py | 通用 Agent 工厂 (AgentScope 2.0 wrapper) |
| knowledge.py | 知识问答 Agent (RAG + 联网搜索) |
| booking.py | 预约 Agent (8 个 booking 工具) |
| business.py | 业务管理 Agent (订单/分店/员工/用户/统计) |
| intent_classifier.py | 顶层意图路由 (knowledge / booking) |

**Backward-compat**: `app/core/*_agent_factory.py` 仍有 shim, 旧 import 继续工作.

## tools/ - 工具集

| 文件 | 作用 |
|---|---|
| registry.py | 工具注册中心 (FunctionTool 自动发现) |
| permission.py | 工具权限分级 (READ / WRITE / HIGH_RISK / DANGEROUS) |
| audit.py | 工具调用审计 (tool_audit_log 表) |
| business_tools.py | 业务工具 (查分店/员工等) |
| order_tools.py | 订单工具 (draft / confirm / cancel) |

**Backward-compat**: `app/core/tool_*.py` 和 `app/core/tools/` 仍有 shim.

## memory/ - 长期记忆

| 文件 | 作用 |
|---|---|
| ltm.py | 跨会话事实提取 + 注入 (核心 API) |
| ltm_v2.py | LTM 增强版 (去重 + 失效 + 语义合并) |
| middleware.py | 接入 chat handler / LangGraph 的中间件 |

**Backward-compat**: `app/core/long_term_memory*.py` 和 `app/rag/middleware/long_term_memory.py` 仍有 shim.

## prompts/ - 提示词模板

| 文件 | 作用 |
|---|---|
| README.md | 索引 + 旧代码位置 |
| knowledge_qa.md | 知识问答 (GeneratePlugin 主用) |
| casual_chat.md | 闲聊 |
| booking_router.md | 预约意图路由 |
| order_parser.md | 订单字段解析 |
| multimodal_trainer.md | 多模态发型师培训 |
| info_extractor.md | 信息抽取 |

**现状**: 文档化, 代码侧后续逐步迁移. 旧 prompt 散落在 app/services/ 和 app/rag/workflow/.

## app/ - FastAPI 服务

| 子目录 | 作用 |
|---|---|
| app/server/ | FastAPI 入口 (api.py, routers/) |
| app/services/ | 业务逻辑 (chat_dispatcher, booking_service) |
| app/db/ | 数据库 (models, session, migration) |
| app/rag/ | RAG 子系统 (v2_engine, chat_pipeline, hybrid) |
| app/auth/ | 鉴权 (JWT, deps) |
| app/embedding/ | Embedding 模型 (硅基流动 / 火山方舟) |
| app/core/ | 跨切关注 (config, metrics, middleware, cache, concurrency) |

## 迁移原则

1. **新代码** 写到顶层 (agents/tools/memory/prompts/skills).
2. **旧代码** 保持 import 兼容, shim 自动 re-export.
3. **彻底迁移** 等所有 caller 改完再删除 shim, 一次 commit.
