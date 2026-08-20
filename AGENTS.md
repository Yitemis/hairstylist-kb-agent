# AGENTS.md — Agent 入口与 Harness

> 借鉴 JavaGuide Harness Engineering §10.1 "OpenAI 实践"：
> **AGENTS.md 当目录，不当手册**（约 100 行），详细规则在 `docs/` 子目录按需加载。
> 渐进式披露（Progressive Disclosure）：启动时只加载元数据，按需读取细节。

---

## 0. 项目一句话

美发行业 **B 端知识助手** + **对话式预约下单**。
两条主流程：
- `knowledge` 路径：用户问专业问题 → RAG 检索 → 引用回答
- `booking` 路径：用户想预约 → **LangGraph 状态机**引导 8 步填字段

---

## 1. 核心入口（按频率从高到低）

| 入口 | 文件 | 说明 |
|------|------|------|
| **Chat 端点** | `app/server/routers/chat_stream.py` | 用户消息入口，dispatch 到 knowledge / booking / casual |
| **Booking 状态机** | `app/rag/workflow/booking_graph.py` | 8 节点 + 4 边，LangGraph 状态机 |
| **Knowledge Agent** | `app/core/knowledge_agent_factory.py` | RAG 检索 + ReAct |
| **Skill 路由** | `app/core/skill.py` | 按 query 路由 + 渐进式披露 |
| **Long-Term Memory** | `app/core/long_term_memory.py` + `app/rag/middleware/long_term_memory.py` | 自动注入 + 自动提取 |
| **中间件** | `app/core/middleware.py` | 日志 / 限流 / RAG |
| **熔断** | `app/core/gateway/model_gateway.py` | pybreaker + FallbackStrategy |

---

## 2. 必读文档（按场景）

### 改 booking 流程前
→ `docs/BOOKING_STATE_MACHINE.md`（完整 LangGraph 状态机设计）

### 改 agent 架构前
→ `docs/AGENT_DEVELOPMENT_PLAYBOOK.md`（JavaGuide 9 篇 + 我们项目 6 层诊断）

### 改 RAG 检索前
→ `docs/LONG_TERM_RAG_ROADMAP.md`（RAG 长期路线图）

### 借鉴 WeKnora 经验
→ `docs/WEKNORA_LEARN.md`

### 项目状态总览
→ `docs/MASTER_ROADMAP.md`（包含 P0-P2 优先级）

### 历史踩坑
→ `docs/PROJECT_AUDIT.md`（v1 清单）+ `docs/PROJECT_OPTIMIZATION_PLAN.md`

---

## 3. 硬约束（Agent 改造时必看）

> 这些是从历史失败里沉淀的，每一行对应一次踩坑。

1. **不动 booking_agent_factory 直接改 booking** → 必须用 LangGraph 状态机（`app/rag/workflow/`）
2. **LTM 不能只写不读** → `extract_facts_with_llm` 必须在 end-of-turn 自动调；`get_user_facts` 必须在 chat 开始时自动注入 system prompt
3. **Skills 不能只注册不用** → `app/core/skill.py` 已有 4 个 Skill，chat 端点必须用 `build_skill_injection(query)` 路由注入
4. **多租户不能丢** → 所有 RAG 查询必须传 `tenant_id` + `audience_filter`
5. **不能写死的 if-else 代替 ReAct** → 路径不确定的任务用 LLM 决策（除非 booking 那种路径确定的用 Workflow）
6. **不能用硬编码 ID** → 分店 / 发型师 ID 必须从 DB 查，不许用 `len(list)+1` 之类的占位
7. **不写超过 500 行的单个 Node** → 大节点拆成小节点 + Edge 串联
8. **失败要可重试** → 每个 Node 必须区分瞬时错误（重试）/ LLM 可恢复错误（塞回 State retry 边）/ 用户可修复错误（停留等输入）

---

## 4. 当前 Agent 能力（6 层 Harness 评分）

| 层 | 评分 | 状态 |
|----|------|------|
| L1 信息边界 | 8/10 | ⚠️ 需写 AGENTS.md（**就是当前文件**） |
| L2 工具系统 | 8/10 | ✅ Skills 真接入；工具描述已升级 |
| L3 执行编排 | 8/10 | ✅ Booking 改 LangGraph 状态机 |
| L4 记忆状态 | 8/10 | ✅ LTM 自动注入 + 自动提取 |
| L5 评估观测 | 1/10 | ❌ Phase 2 才做 |
| L6 约束恢复 | 4/10 | ⚠️ 熔断有，HITL 未完整接入 |
| **合计** | **37/60 (62%)** | **Level 2 稳定** |

> 完整诊断见 [AGENT_DEVELOPMENT_PLAYBOOK.md §11](docs/AGENT_DEVELOPMENT_PLAYBOOK.md)

---

## 5. 范式选型

| 子任务 | 范式 | 理由 |
|--------|------|------|
| 顶层路由 | 分类器 → 多 Agent | intent_classifier 分发 |
| 预约下单 | **Agentic Workflows** | 11 步硬序列 + 局部 ReAct 解析 |
| 知识问答 | **ReAct** | 路径不确定 |
| RAG 检索 | **Sub-agent 隔离** | 主 Agent 不见全 chunk |
| 知识答案 | **Reflection** | 校验不幻觉（Phase 2 接入） |
| 闲聊 | 单轮 LLM | 无工具无状态 |

---

## 6. 工具权限分级（L6 P0）

| 等级 | 工具 | 风险 |
|------|------|------|
| **READ** | `search_hair_knowledge` / `list_branches` / `list_stylists` | 低 |
| **WRITE** | `create_draft_order` / `update_order_fields` | 中（可改草稿） |
| **HIGH_RISK** | `confirm_order` | **高**（需 HITL 确认） |
| **DANGEROUS** | （未来：删除订单 / 退款） | **极高**（必须人工） |

---

## 7. 不要做的事

- ❌ 不要在 `app/server/routers/` 写业务逻辑 → 放 `app/services/`
- ❌ 不要 hardcode user_id → 全部从 `ctx.user_id` 取
- ❌ 不要把 system prompt 写在 `api.py` 里 → 放 `app/core/` 工厂
- ❌ 不要让 LLM 输出直接进 DB → 走工具 + 校验
- ❌ 不要混用 AgentScope 和 LangGraph → booking 用 LangGraph，其他用 AgentScope
- ❌ 不要在生产环境用 MemorySaver → 用 PostgresSaver / Redis state_store

---

## 8. 借鉴来源

| 来源 | 应用 |
|------|------|
| **JavaGuide agent/ 9 篇** | Agent 范式 / Harness / Skills / Workflow / Memory / Loop |
| **JavaGuide rag/ 5 篇** | RAG 6 环节 / Hybrid Search / Rerank / 评估 |
| **WeKnora §5** | StuckLoopDetector / EnrichedPassage |
| **九阳 POC** | PDF 双引擎解析（PyMuPDF + MinerU） |
| **AgentScope 2.0** | 中间件 / 状态持久化 / 工具系统 |
| **OpenAI 实践** | AGENTS.md 当目录 + Linter 自带修复 |
| **Anthropic 实践** | Context Resets + 渐进式披露 |

---

## 9. 联系 / 反馈

- 改 Agent 行为出问题 → 查 `docs/PROJECT_AUDIT.md` + `docs/AGENT_DEVELOPMENT_PLAYBOOK.md`
- 改 RAG 检索 → 查 `docs/LONG_TERM_RAG_ROADMAP.md` + `docs/WEKNORA_LEARN.md`
- 改前端 → 查 `docs/FRONTEND_PROMPTS.md` + `CLAUDE.md`

> **金句**（来自 JavaGuide）：
> "**大部分 Agent 项目跑起来不稳定，不是模型不够好，是基础没搭好。**"
> "**如果你自己都说不清怎么验收，就别急着 loop。先把目标拆小，把验收标准写出来。**"
