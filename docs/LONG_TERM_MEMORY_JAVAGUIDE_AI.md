# JavaGuide AI 完整学习笔记

> 来源：E:\JavaGuide-main\docs\ai\（Alibaba/Snailclimb 维护的 AI 完整教程）
> 对应我们项目：E:\hairstylist-kb-agent
> 学习完成：JavaGuide AI 全部 18 篇文档

---

## 0. 总览：JavaGuide AI 体系

5 大主题：

| 主题 | 路径 | 我们用得上的点 |
|------|------|------------|
| AI 核心概念 | ai/ai-core-concepts.md | LLM/Token/Agent/ReAct/RAG/MCP/Skill 概念地图 |
| RAG 体系 | ai/rag/* | 文档处理、向量库、检索优化、知识更新、GraphRAG |
| Agent 体系 | ai/agent/* | Agent Loop/Prompt/Context/Memory/Harness/Skills |
| LLM 基础 | ai/llm-basis/* | LLM 运行机制/结构化输出/Function Calling/评测 |
| 系统设计 | ai/system-design/* | AI 应用架构/LLM Gateway |

---

## 1. LLM 基础（关键概念）

### 1.1 Token 与上下文窗口
- 模型每"补"一个 Token 是一次前向（自回归生成）
- 上下文窗口 ≠ 实际可用：还要扣除 system prompt、history、tool schema、输出预算
- 痛点：客服对话+订单详情+ RAG 检索结果，长上下文会让模型失焦

### 1.2 采样参数
- Temperature/Top-p 控制随机性
- 客服场景：低 temperature（0.2-0.5）保稳定

### 1.3 Prompt 四要素
- Role / Task / Context / Format
- 我们的 system prompt 缺 **Format**（输出格式约束）

### 1.4 结构化输出
- JSON Mode 只管"是 JSON"，不管"字段对不对"
- JSON Schema 是契约
- Structured Outputs 把约束前移到模型生成阶段
- Function Calling = 模型生成调用意图 + 业务侧执行

### 1.5 LLM-as-a-Judge
- 自动评估不是裁判真理
- 上线前必须抽样人工复核
- 我们的 RAG / Chat 没有评估机制

---

## 2. RAG 体系（最关键）

### 2.1 RAG 文档处理 6 环节 + 3 校验

| 环节 | 典型问题 | 我们的现状 |
|------|---------|----------|
| 文件上传 | 格式伪造、大小超限、编码混乱 | 没做格式校验 |
| 格式校验 | 扩展名和 MIME 不符 | 没做 |
| Layout 解析 | PDF 多栏、表格合并、页眉页脚 | **没做！只接受 str** |
| 清洗去噪 | 乱码、特殊字符、目录残留 | 没做 |
| Chunking | 语义截断、上下文断裂 | 父子分块（仅纯文本） |
| Metadata | 没保存来源、页码、版本 | 有 tenant/document_id，没 page/章节路径 |
| 入库 | 向量维度不一致 | OK |

3 道校验：格式 → 解析 → Chunking 质量
**我们 0 道校验**

### 2.2 Chunking 策略表

| 文档类型 | 推荐 | 我们的支持 |
|----------|------|----------|
| Markdown | 按 H1/H2/H3 | 没特殊处理 |
| HTML | 按标签层级 | 没 |
| PDF | 按页/章节（LlamaParse/Docling） | **没** |
| 表格 | 单独成块不切散 | 没 |
| 代码 | 按函数/类/包 | 没 |
| 纯文本 | Parent-Child 512/128 | OK |

**我们只有 1/6 种 Chunking 策略**。

### 2.3 父子分块（Parent-Child Chunk）

> 用 300 Token 子块做向量检索，挂到 1200 Token 父段落上。检索时先命中小块，再把对应父段落放入上下文。

我们 128/512 偏小，推荐 300/1200。但要按文档类型调。

### 2.4 Hybrid Search（生产默认）

向量擅长语义，BM25 擅长精确词（错误码、SKU、专有名词）。

| 查询类型 | 向量 | BM25 |
|----------|------|------|
| "如何取消订阅" | 匹配"关闭自动续费" | 无 |
| "错误码 E1027" | 召回泛化 | 精确命中 |
| "ABX-4421 型号参数" | 无 | 精确命中 |

**我们 100% 纯向量，缺 BM25**。错误码/产品型号/染发编号"色号 7.3"都查不到。

### 2.5 Query Rewrite 6 策略

- 规范化改写
- Multi-Query
- Query Decomposition
- Step-back Query
- HyDE
- Self-Query

**我们 0 个**。用户问"我那个 7.3 的红色掉色了"无法检索。

### 2.6 Top-K 三段（不是越大越好）

- `recall_top_k`：粗召回 30-100
- `rerank_top_n`：重排后 5-10
- `context_top_n`：最终入 Prompt 3-6

**我们只有一个 top_k**。

### 2.7 Rerank 价值

向量相似度 ≈ "这两段话语义接近吗"
Rerank ≈ "这段话能不能回答这个问题"

**我们的 Rerank**：已接入但实际降级（用户没配 RERANK_API_KEY 静默降级到向量分数，没告警）。

### 2.8 上下文压缩 3 种

- 选择性抽取（漏隐含条件）
- 查询相关摘要（引入改写偏差）
- 结构化抽取（依赖 Schema）

**我们 0 个**。

### 2.9 评估指标（4 大类）

- 召回：Hit Rate@K、MRR、Context Recall
- 精度：Context Precision
- 生成：Faithfulness、Answer Relevancy
- 工程：Latency、Cost、Token

**我们 0 个**。靠感觉调参是 RAG 优化最大禁忌。

### 2.10 GraphRAG

适合多跳关系、跨文档归纳。我们不需要。

### 2.11 5 类常见错误

| 错误 | 我们中招 |
|------|---------|
| 只调 embedding | 没真做评估 |
| 不做评估 | 中招 |
| 盲目扩大 Top-K | 没考虑 |
| 塞无关上下文 | 部分中招 |
| 忽略拒答能力 | 没做 |

---

## 3. Agent 体系

### 3.1 Agent = Model + Harness

Harness = Prompt + Tools + Memory + Sandbox + Middleware + Skill + Loop + State

Harness 不是替代 Prompt，是包在最外面的环境。三者关系：
- **Prompt**：指令本身怎么写
- **Context**：该给 Agent 看什么
- **Harness**：系统怎么持续执行纠偏

**我们 Harness 不完整**（缺 Skills/沙箱/HITL/完整中间件）

### 3.2 Harness 六层架构

| 层 | 解决 | 我们 |
|----|------|------|
| L1 信息边界 | Agent 该知道什么 | 有 system prompt |
| L2 工具系统 | 怎么和外部交互 | 有 Toolkit 不全 |
| L3 执行编排 | 多步骤怎么串 | 没显式编排 |
| L4 记忆状态 | 长任务怎么管理 | chat_messages + sessions |
| L5 评估观测 | 怎么知道做对了 | 有 metrics 端点没用 |
| L6 约束恢复 | 出错怎么办 | **没有** |

### 3.3 Agent Loop

```
读取上下文 → LLM 推理 → 调用工具/回答 → 把工具结果写回 → 循环
退出条件：不再调工具 / 达到 max_iter
```

我们：booking 流程不是真 ReAct，是关键词匹配 + 业务调度
- 优点：稳定、可控
- 缺点：用户说"造型烫"会卡（已修），复杂任务容易跑偏

### 3.4 ReAct vs Plan-and-Execute

| 模式 | 特点 | 适用 |
|------|------|------|
| ReAct | 边想边做 | 探索性任务 |
| Plan-and-Execute | 先规划再执行 | 步骤多、依赖明确 |
| 混合 | 全局 Plan + 局部 ReAct | 复杂任务 |

我们：纯业务调度（类似硬编码 Plan）。ReAct 只用于 knowledge 路径。

### 3.5 Context Engineering 5 指标

- 任务成功率、工具质量、上下文成本、延迟、结果质量

**我们 0 个指标在用**（prometheus_client 装了但没暴露 metrics）

### 3.6 短期记忆 vs 长期记忆

| 类型 | 范围 | 我们 |
|------|------|------|
| 短期 | Session 内 | chat_messages |
| 长期 | 跨 Session | user_profiles 表存在但只 extract + store，**没读取** |

我们的长期记忆问题：
- long_term_memory.py 写了 extract_facts_with_llm
- 但**没有自动从 chat 里提取**
- **没有自动注入 system prompt**
- 用户在客服那里"我喜欢韩式剪发"，下周新对话完全不知道

### 3.7 长期记忆 vs RAG 区别

- RAG：共享知识源（公司规章、产品文档），不个性化
- 长期记忆：用户专属偏好

我们 RAG 做的是对的（产品知识），但长期记忆**没真正落地**。

### 3.8 Memory 操作生命周期

编码 → 存储 → 提取 → 巩固 → 反思 → 遗忘

**我们只做了存储**。缺：编码（LLM 提取）、巩固（短期转长期）、反思（提取经验）、遗忘（淘汰低价值）。

### 3.9 Agent Skills 是什么

> Skill 是把"老员工脑子里的规矩"写进 SKILL.md，按需加载到上下文。

层次关系：
- Prompt：用户说什么
- Function Calling：模型怎么调工具
- MCP：工具从哪来
- **Skill**：怎么调 + 什么时候不调

**我们的 Skill 实现**：
- app/core/skill.py 有 Skill 类 + SkillRegistry
- 4 个预置技能
- **但实际没在 agent 中使用**（chat 端点没用 skill middleware）

### 3.10 SKILL.md 怎么写

```yaml
---
name: pdf-extraction
description: 从 PDF 提取文本和表格。当用户提及 PDF、文件提取、文档解析时使用。
---
# 正文
## 步骤
1. ...
## 边界
- 不要做 X
- 错误时 Y
```

原则：500 行以内、写"做什么+什么时候用"、别写科普。

### 3.11 渐进式披露（Progressive Disclosure）

启动只加载元数据（name + description）。匹配后才读 SKILL.md 正文。需要细节再读 references/。

类比：到新城市，先看地图，**不背整本旅游指南**。

**我们 Skill 现状**：4 个技能元数据 + 正文都全量加载到 system prompt（没做"按需匹配"）。

### 3.12 Loop Engineering

> 围绕 Agent 设计可持续运行的反馈循环：触发/目标/上下文/行动/观察/状态/停止。

关键：**回放**。每次改动后，用同一批问题跑一遍比较指标。没有回放，调参就是玄学。

**我们 0 个回放能力**。

### 3.13 上下文利用率的 40% 阈值

| 区间 | 表现 |
|------|------|
| 0-40% | Smart Zone：推理聚焦、工具调用准确 |
| >40% | Dumb Zone：幻觉增多、兜圈子 |

建议：监控上下文利用率，超 40% 触发压缩/分段。

---

## 4. 系统设计

### 4.1 LLM Gateway 架构

> 统一入口，路由到不同模型/供应商，限流/计费/审计。

**我们没做**。每个调用都直连火山方舟，没有中间层。

### 4.2 AI 应用通用架构

```
用户 → 接入层(API Gateway) → 业务编排层 → Agent 层 → 模型层
                                      ↓
                                数据层(向量库/业务DB)
                                      ↓
                                可观测性(日志/指标/Trace)
```

我们的层级：
- 接入层（FastAPI）
- 业务编排层（写在 chat 端点里，没分离）
- Agent 层（knowledge_agent + main agent）
- 模型层（ChatModel + EmbeddingModel）
- 数据层（SQLite + Qdrant）
- **可观测性：prometheus 没接**

---

## 5. JavaGuide 给我们的关键启示

### 5.1 RAG 是系统工程，不是单点调参

> 真正有效的调优，必须沿着完整链路拆：
> 数据决定上限 → Chunk 决定召回粒度 → Hybrid 提升稳健性 → Query Rewrite 解决表达差异 → Rerank 决定证据顺序 → 上下文工程决定信噪比 → 评估决定能否持续优化

**我们现状**：断链严重。

### 5.2 失败样本驱动优化

> 改一个，加进评估集。RAG 系统最怕"修 A 坏 B"。只有失败样本持续沉淀，系统才会越调越稳。

**我们**：评估集为空（0 个评估样本）。

### 5.3 排查路径

```
失败样本
  ↓
1. 正确证据进入候选池？  →  否：查召回（解析/Chunk/Metadata/Query Rewrite/Hybrid）
  ↓ 是
2. 正确证据排名靠前？   →  否：查 Rerank
  ↓ 是
3. 上下文正确？           →  否：查去重/压缩/排序
  ↓ 是
4. 模型正确回答？         →  否：查 Prompt/上下文排序
```

**我们 0 个能力诊断**。

### 5.4 知识更新（我们要做的）

- 增量索引：不重建整个库
- TTL：过期文档自动降权
- 冲突检测：同主题多版本识别
- 手动回滚：错误索引能撤回

**我们**：不支持增量更新，每次全量重建。

### 5.5 棕地项目改造（最大挑战）

> 把一个 10 年代码库接入 Harness 比从零搭难 10 倍。

**我们项目就是棕地**，没有强类型系统、缺乏明确架构约束。Harness 推起来会很难。

---

## 6. 我们的项目 vs JavaGuide 标准的差距

| 维度 | JavaGuide 标准 | 我们 | 差距 |
|------|--------------|------|------|
| 文档解析 | 6 环节 + 3 校验 | 0 环节 | -60% |
| Chunking 策略 | 6 种按文档类型 | 1 种（纯文本） | -83% |
| Hybrid Search | 必备 | 0 | -100% |
| Query Rewrite | 6 策略 | 0 | -100% |
| Rerank | 完整链路 | 静默降级 | -50% |
| 上下文压缩 | 3 种 | 0 | -100% |
| 评估指标 | 4 大类 | 0 | -100% |
| Agent Loop | 真正的 ReAct | 业务调度 | 失配 |
| Context 管理 | 3 种压缩 | 0 | -100% |
| Memory | 6 阶段 | 只 1 阶段 | -83% |
| Skills | 渐进式披露 | 全量加载 | 失配 |
| Harness 6 层 | 完整 | 1-2 层 | -67% |
| Loop Engineering | 7 要素 | 0 | -100% |
| 可观测性 | 完整 | 仅 1 端点 | -80% |

**我们当前在"Level 0-1"之间**（基础约束缺失，靠运气）。
**要进入 Level 2**（反馈回路），需要至少补 5 个能力：
1. 文档解析（PDF/Word）
2. Hybrid Search
3. 评估集 + 回放
4. 真正的 Agent Loop（booking 流程用 ReAct）
5. Skills 渐进式披露
