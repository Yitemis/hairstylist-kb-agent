# Complete Project Optimization Plan

> Sources: E:\agentscope-main, E:\agentscope-java-main, E:\JavaGuide-main\docs\ai

---

## Overview: Module-Segregated Optimization Tasks

6 modules:

- L0 Database (DB/Schema)
- L1 RAG Module (knowledge base pipeline)
- L2 Agent Module (dialogue system)
- L3 LLM Module (model calls)
- L4 Frontend/Backend
- L5 DevOps (deploy/observability)
- L6 Business (order/auth)

Priority: P0 (blocks biz/security), P1 (immediate UX), P2 (long-term), P3 (nice-to-have)

---

## Module L0: Database

### L0-P0-01: Schema evolution
- Problem: create_all doesnt update existing tables
- Risk: Field changes in models.py wont apply to existing DB
- Fix: Integrate Alembic (done but not auto-run)
- Workload: 2h

### L0-P0-02: Incremental upsert
- Already supported via document_id unique key
- Workload: 1h

---

## Module L1: RAG (most critical)

### L1-P0-01: Document parsing (TOP MISSING)
- Problem: Only accepts str! No PDF/Word parsing
- Fix: Add parsers/ submodule with PDF (Docling/LlamaParse), Word (python-docx), Excel (openpyxl)
- Workload: 2-3 days

### L1-P0-02: Document-type chunking
- Markdown: H1/H2/H3
- PDF: per page/chapter
- Code: per function/class
- Tables: standalone
- Workload: 2 days

### L1-P0-03: 3-tier validation
- Format check, Parse check, Chunking quality check
- Workload: 1 day

### L1-P1-01: Hybrid Search (vector + BM25)
- Problem: Pure vector, cant find error codes/SKUs
- Fix: Add jieba + BM25 + RRF fusion
- Workload: 1.5 days

### L1-P1-02: Query Rewrite
- Problem: User colloquial queries cant be retrieved
- Fix: 6 strategies (normalization/Multi-Query/Decomposition/Step-back/HyDE/Self-Query)
- Workload: 1 day

### L1-P1-03: Context compression
- Selective extraction / query-related summary / structured extraction
- Workload: 1 day

### L1-P1-04: Knowledge update (incremental + TTL)
- Upsert by document_id, version numbering, stale detection
- Workload: 1.5 days

### L1-P1-05: Evaluation set (RAG optimization prerequisite)
- 50 hand-crafted questions: 20 high-freq, 10 failed, 10 exact-match, 5 reject, 5 multi-hop
- Metrics: Context Recall, Context Precision, Faithfulness, Answer Relevancy
- Workload: 1.5 days

---

## Module L2: Agent

### L2-P0-01: Booking uses real ReAct Agent
- Problem: Current booking uses keyword matching, not ReAct
- Fix: Register 5 order tools to main Agent, let LLM decide
- Keep keyword matching as fallback
- Workload: 2 days

### L2-P0-02: Long-term memory actually works
- Problem: user_profiles table exists but never read
- Fix: Auto-extract facts after each chat, auto-inject at new chat start
- Strict user_id isolation
- Workload: 1 day

### L2-P1-01: Skill progressive disclosure
- Problem: app/core/skill.py exists but unused
- Fix: SkillMiddleware: load metadata first, match by vector similarity, only inject matched skills
- Workload: 1.5 days

### L2-P1-02: HITL for confirm_order
- Problem: confirm_order directly submits without user confirmation
- Fix: confirm_order triggers ASKING, frontend shows modal, resolve_ask on user click
- Workload: 1.5 days

### L2-P1-03: Loop Engineering
- trace_id for all calls, replay script for A/B testing
- Context utilization monitor (alert at 40%)
- Workload: 1.5 days

---

## Module L3: LLM

### L3-P0-01: Streaming LLM
- Problem: 5-10s white screen
- Fix: chat endpoint uses SSE, model stream=True
- Workload: 1.5 days

### L3-P1-01: LLM Gateway
- Unified entry, rate limit, billing, model routing
- Fallback chain: Volcengine -> DeepSeek -> Zhipu
- Workload: 2 days

### L3-P1-02: Structured output (Function Calling)
- Problem: chat returns naked string
- Fix: Use Function Calling (not JSON Prompt)
- Workload: 1 day

---

## Module L4: Frontend

### L4-P0-01: Frontend SSE integration
- Backend SSE exists, frontend doesnt use it
- Fix: ChatPage uses EventSource
- Workload: 1 day

### L4-P1-01: H5 mobile UI fix
- CSS media query strict control
- Workload: 0.5 day

### L4-P1-02: Knowledge base admin UI
- Upload docs, trigger indexing, see status
- Workload: 2 days

---

## Module L5: DevOps

### L5-P0-01: Prometheus metrics integration
- Problem: prometheus_client installed but no metrics exposed
- Fix: /metrics endpoint, key metrics, Grafana dashboard
- Workload: 1.5 days

### L5-P0-02: Structured logging
- Problem: Text logs, hard to parse
- Fix: JSON format with trace_id/user_id/session_id, integrate Loki/ELK
- Workload: 1 day

### L5-P1-01: Real Docker deploy
- Dockerfile written but never tested
- Fix: docker build + docker-compose with nginx + HTTPS
- Workload: 1 day

### L5-P1-02: Alembic auto-migration
- Auto-run alembic upgrade head on startup
- Workload: 0.5 day

### L5-P1-03: CI/CD
- GitHub Actions: lint + test + build + deploy
- Workload: 1 day

---

## Module L6: Business

### L6-P0-01: JWT secret startup check
- Status: DONE

### L6-P1-01: Draft order expiration
- Auto-delete drafts > 7 days
- Workload: 0.5 day

### L6-P1-02: SMS verification
- Integrate Aliyun SMS or Tencent SMS
- Workload: 1 day

### L6-P1-03: Business hours check
- 23:00-09:00 cant order
- Workload: 0.5 day

### L6-P2-01: Review system
- Post-appointment user review
- Workload: 2 days

---

## Execution Roadmap

### Stage 1: Foundation (1-2 weeks)
- L1-P0-01, L1-P0-02, L1-P0-03: Document parsing + chunking + validation
- L1-P1-01, L1-P1-05: Hybrid Search + Evaluation
- L2-P0-01, L2-P0-02: Real ReAct + Long-term memory
- L5-P0-01, L5-P0-02: Metrics + Logging
- Total: ~14 days

### Stage 2: Capability Deepening (2-3 weeks)
- L1-P1-02, L1-P1-03, L1-P1-04: Query Rewrite + Compression + Update
- L2-P1-01, L2-P1-02, L2-P1-03: Skills + HITL + Loop
- L3-P0-01, L4-P0-01: Streaming + Frontend SSE
- Total: ~11 days

### Stage 3: Enterprise Polish (ongoing)
- L1-P1-04, L2-P1-*, L3-P1-*, L4/L5/L6 remaining

---

## Module Ownership

| Module | What Exists | What's Missing | Priority |
|--------|------------|----------------|----------|
| L0 Database | SQLAlchemy 2.0 async, Alembic | Auto-migration, TTL | L0-P0 |
| L1 RAG | Parent-child, vector store, Self-RAG | Parse, Hybrid, Rewrite, Compress, Eval | L1-P0/P1 all |
| L2 Agent | Business dispatch, ReAct (knowledge only) | ReAct for booking, Memory, Skills, HITL, Loop | L2-P0/P1 all |
| L3 LLM | OpenAIChatModel, Embedding | Streaming, Gateway, Structured output | L3-P0/P1 |
| L4 Frontend | Figma design + integration | SSE, H5 fit | L4-P0 |
| L5 DevOps | Dockerfile, metrics (unconnected) | Metrics integration, Logging, CI/CD | L5-P0 |
| L6 Business | Auth, orders, CRUD | Draft expiry, SMS, business hours | L6-P1 |

---

## Key Decisions

### Decision 1: LlamaParse vs Docling?
Answer: Docling first (free, local), LlamaParse as fallback
Cost: LlamaParse $0.001/page, Docling free
Validation: Test on 10 sample PDFs before full rollout

### Decision 2: Hybrid Search implementation?
Answer: Self-implement BM25 + RRF, not ElasticSearch
Reason: Knowledge base < 100K chunks, jieba + Python sufficient

### Decision 3: Evaluation set size?
Answer: 50 hand-written, expand to 500 in 6 months
Allocation: 20 high-freq, 10 failed, 10 exact-match, 5 reject, 5 multi-hop

### Decision 4: GraphRAG?
Answer: NO, not now
Reason: Multi-hop questions < 5% of our traffic

### Decision 5: Booking uses ReAct?
Answer: YES, with hard-coded fallback
Reason: ReAct handles edge cases, hard-coded provides stability

---

## 12. 增量更新（来自九阳 POC 实战经验 2026-06）

> 来源：C:\Users\18414\Desktop\阿里-九阳产品智慧大脑POC验证报告.docx
> 　　　C:\Users\18414\Desktop\九阳产品智慧大脑POC测试报告.docx
> 价值：直接的企业级 RAG + Multi-Agent POC 实战调优数据（33个 query 100% 命中）

### 12.1 九阳 POC 关键发现

**真实业务中 12 类场景的实战分布：**
- 文本检索（5题）：chunk 切分大小很重要
- 表格检索（6题）：占 1/4 业务量，必须特殊处理
- 图文混排（2题）：图片召回与文字必须一起
- 复杂表格（3题）：合并单元格是难点
- 横版 PDF（2题）：**失分最多的场景（4题）**
- 章节定位（1题）：按 section 前缀定向召回
- 权限隔离（1题）：文档标签 + Prompt 拒答双保险
- 产品对比（1题）：多轮 RAG 跨文档
- 业务排查（3题）：故障树 Prompt + 上下文记忆
- 反问机制（1题）：型号不明确时反问

**九阳 POC 文档解析参数（实战值）：**
- chunk_size: **800 字符**（不是 512/128！）
- overlap: **80 字符**（10%）
- 切分策略：**按 ## 标题层级切分**（不是固定长度）
- chunk 标签：**chapter**（按章节前缀检索）
- 元数据：tenant_id、permission_tag、category、page
- 表格处理：xlsx 转 Markdown 长表（每行 1 切片）
- 合并单元格：完整展开 533 个（D525 案例）

### 12.2 对 L1 解析模块的具体调整

**L1-P0-01 文档自动解析补充**：

九阳 POC 实战调优顺序：
1. **按 ## 切分**（不是固定长度）→ 解决 4.6 章节定位
2. **Q&A 速答段冗余** → 解决 4.1 文本长文档事实定位
3. **横版 PDF + OCR 兜底** → 解决 3.1 失分最多的 4 题
4. **合并单元格完整展开** → 解决 4.3 复杂表格
5. **图片 alt 描述 + COS 外链** → 解决 4.4 图文混排
6. **表格转 Markdown 长表** → 解决 4.2 表格类

**L1-P1-05 评估集调整**：

九阳 POC 提供 33 个 query 模板，按 12 类场景分配：
- 文本类 5 题（##切分 + 速答段）
- 表格类 6 题（合并单元格 + 角色区分）
- 复杂表格 3 题（图片+表格）
- 图文混排 2 题（alt + COS）
- OCR 1 题（图片内文字）
- 章节定位 1 题（section 前缀）
- 产品对比 1 题（跨文档 RAG）
- 业务排查 3 题（多轮）
- 权限隔离 1 题（拒答）
- 横版 PDF 2 题（特殊版式）
- 反问机制 1 题（型号反问）
- 简单 Excel 2 题（快递价格）
- 加分项 5 题（图文混排/Mermaid/音频/PDF生成）

### 12.3 对 L2 Agent 模块的具体调整

**L2-P0-01 Booking 用 ReAct 补充**：

九阳 POC 用的 5 层 Multi-Agent 架构：
```
用户 → 接入层 → JY-Router(主控)
         ├→ JY-Compare (跨文档对比)
         ├→ JY-DocGen (PDF 生成)
         ├→ JY-Aftersales (客服)
         ├→ JY-Policy (制度/权限)
         └→ KnowledgeRetrievalAnswer (RAG 检索)
```

**我们的简化版**：
- 单 Agent + 关键词匹配 booking（暂够用）
- 未来加 JY-Policy 类（权限专用 Agent）
- 未来加 JY-DocGen 类（自动生成文档）

**L2-P1-02 HITL 补充**：

九阳 POC 的反问机制（4.11）：
- 用户问"破壁机不启动了"
- JY-Router 识别为通用品类
- 自动反问："请问是 K7Pro、D525 还是 D650？"
- **不要在 ambiguous 时硬猜**

我们的 booking 流程也要加：
- 用户没说分店时 → 列表选项
- 用户没说发型师时 → 列表选项
- 用户没说服务时 → 推荐 + 选项
- 用户没说日期时 → 反问
- **已经在做了！**（_continue_editing 和选项卡片）

**L2-P1-04 长期记忆补充**：

九阳 POC 的用户偏好：
- 部门：sales / support / it / management / hr
- 敏感度：public / internal / confidential / secret
- 地域：cn-east / cn-south / cn-north
- 产品线：beanmilk / blender / water / kettle

我们的 user_profiles 可以扩展这些维度

### 12.4 对 L6 业务模块的具体调整

**L6-P1-04 权限隔离（4 步实施，立即可做）**：

Step 1 - 文档打标签：
- 在 orders 表加 permission_tag 字段
- 公开数据：public
- 内部数据：A / B / public
- 机密数据：secret / confidential

Step 2 - API 层过滤：
- GET /api/orders：按 user role 过滤
- 公开订单：所有用户可见
- 内部订单：仅本部门和 admin 可见

Step 3 - visitor_labels 硬隔离：
- JWT 解析 role（user/staff/admin）
- staff 默认 role=B
- admin 默认 role=A
- user 默认 role=public

Step 4 - Prompt 拒答兜底：
- 召回为空时不允许编造
- 标准话术："抱歉您当前角色无权访问该资料"
- 严禁泄露受限文档存在的事实

**L6-P1-05 多模态预处理（生产化）**：

九阳 POC 的 xlsx 预处理：
- 533 合并单元格 → 转 MD → 切片 28 个 → 100% 召回
- 脚本：scan + 转 MD + caption 绑定
- 我们要做：D525 这种复杂 xlsx 必须预处理

**L6-P2-04 DocGen（PDF 生成）**：

九阳 POC 加分项：
- 用户说"生成 K7Pro 紫火版用户手册 PDF"
- DocGen：检索知识库 → 组装 MD → PDF 生成 → URL
- 价值：把扫描版 PDF 说明书（不可检索）自动重写为可检索 MD
- 新品上市文档时效缩短 90%
- **这是高价值的差异化能力**

### 12.5 对 RAG 检索的具体调整

**L1-P1-06（新增）section 前缀定向召回**：

九阳 POC 章节定位最佳实践：
- 文档解析时给每个 chunk 加 chapter 标签
- 用户问"第3节" → 检索时只召回 chapter=3 的 chunks
- 大幅提高召回精度
- 我们的 chat_messages 没这个字段，需加

**L1-P1-07（新增）Q&A 速答段冗余**：

九阳 POC 加分项：
- 在 MD 文档中追加 Q&A 速答段
- "Q: 800ml 五谷浆要多久？ A: 29 分钟"
- 即使原文没说，速答段也直接命中
- 关键事实强冗余编码
- 我们要在 Chunking 阶段加这个能力

**L1-P1-08（新增）横版 PDF 处理**：

九阳 POC 失分最多的场景：
- 横版折页、左右分栏、表格嵌套图片
- 方案：开启 OCR + PDF 旋转预处理
- vision 整页描述为兜底
- 任何版面布局下信息不丢失
- **我们必须做：PDF 第一关就 OCR 兜底**

### 12.6 对前端的调整

**L4-P1-03（新增）Mermaid 流程图渲染**：

九阳 POC 实践：
- 知识库中的流程图以 Mermaid 代码形式保存
- 前端原生渲染为可视化流程图
- 优势：无需 COS 图床、节省存储、代码可编辑
- 实现：JY-Policy Prompt 强制 mermaid 代码块包裹
- 我们前端加 Mermaid 渲染（react-flow / mermaid.js）

**L4-P1-04（新增）音频混排**：

九阳 POC 实践：
- 客服录音以音频外链形式嵌入答案
- 业务价值：客服培训听标杆、争议引用原话
- 实现：原 HTML 音频链接 → markdown 链接 + HTML5 audio
- 我们前端加 audio 组件

### 12.7 立即可做的 5 个 P0 改进（按九阳经验）

1. **按 ## 切分 Markdown 文档**（解决 4.1/4.6 章节定位）
   - 位置：app/rag/chunkers/
   - 工作量：1 天

2. **chunk_size 调大到 800+80**（九阳实战值）
   - 位置：app/rag/chunkers/parent_child_chunker.py（已有，改参数）
   - 工作量：0.5 天

3. **横版 PDF + OCR 兜底**（解决 4.10 失分）
   - 位置：app/rag/parsers/pdf_parser.py（新建）
   - 工作量：2 天（PDF + OCR 集成）

4. **合并单元格完整展开**（解决 4.3 复杂表格）
   - 位置：app/rag/parsers/excel_parser.py（新建）
   - 工作量：1.5 天

5. **图片 alt 描述 + COS 外链**（解决 4.4 图文混排）
   - 位置：所有解析器统一加 image_info 处理
   - 工作量：0.5 天

**5 个 P0 总工作量：5.5 天**

### 12.8 立即可做的 5 个 P1 改进

1. **Q&A 速答段冗余**（chunk 解析后追加）
2. **章节 chapter 标签**（chunk metadata）
3. **文档 permission_tag 字段**（orders 表 + chat_messages 表）
4. **xlsx 转 Markdown 长表**
5. **JWT role + visitor_labels 硬隔离**

**5 个 P1 总工作量：4 天**

### 12.9 立即可做的 4 个 P2 改进（加分项）

1. **Mermaid 流程图前端渲染**
2. **音频混排前端**
3. **PDF DocGen（PDF 生成）**
4. **反问机制**（模型自动反问型号）

**4 个 P2 总工作量：5 天**

### 12.10 完整 4 资料学习体系

我已学完 4 份学习资料：

| 资料 | 路径 | 长期记忆 |
|------|------|---------|
| AgentScope 2.0 Python | E:\agentscope-main | docs/LONG_TERM_MEMORY_AI_AGENT.md |
| AgentScope 2.0 Java | E:\agentscope-java-main | （与上面同）|
| JavaGuide AI 教程 | E:\JavaGuide-main\docs\ai | docs/LONG_TERM_MEMORY_JAVAGUIDE_AI.md |
| ekbs-ai-service 文档解析 | D:\Joyoung\ekbs-ai-service | docs/LONG_TERM_MEMORY_EKBS_AI_SERVICE.md |
| 九阳 POC 实战 | C:\Users\18414\Desktop\九阳*.docx | docs/LONG_TERM_MEMORY_JOYOUNG_POC.md |

**互相印证**：
- AgentScope 的 5 层架构 ↔ 九阳 5 层架构（接入/路由/能力/知识/基础）
- JavaGuide 6 环节 ↔ 九阳 12 类场景的实战化
- JavaGuide 评估集 ↔ 九阳 33 个 query 模板
- ekbs 文档解析 ↔ 九阳 12 类场景的解析策略
- AgentScope Skills ↔ 九阳 加分项能力
- ekbs LLMBundle ↔ 九阳 5 类 LLM 调度

最终输出：**完整优化 plan = PROJECT_OPTIMIZATION_PLAN.md**（含 6 模块 × P0/P1/P2 = 50+ 任务）