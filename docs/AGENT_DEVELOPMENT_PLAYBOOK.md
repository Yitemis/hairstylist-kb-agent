# Agent 开发实战手册（基于 JavaGuide 深度学习 + 我们项目反思）

> 来源：`E:\JavaGuide-main\docs\ai\agent\` 9 篇文档
> 定位：**"怎么把 Agent 真正做稳"** 的方法论 + 我们项目的差距诊断
> 对应项目：`E:\hairstylist-kb-agent`（美发知识助手）
> 关联文档：[LONG_TERM_MEMORY_JAVAGUIDE_AI.md](LONG_TERM_MEMORY_JAVAGUIDE_AI.md)（总览）/ [PROJECT_AUDIT.md](PROJECT_AUDIT.md)（旧清单）

---

## 📑 目录

- [0. 核心论点](#0-核心论点)
- [1. Agent 范式选择：ReAct / Plan-and-Execute / Workflow / Multi-Agent](#1-agent-范式选择)
- [2. Harness Engineering 六层架构](#2-harness-engineering-六层架构)
- [3. Context Engineering：上下文是 Agent 的工作记忆](#3-context-engineering上下文是-agent-的工作记忆)
- [4. Skills：把"老员工脑子里的规矩"沉淀下来](#4-skills把老员工脑子里的规矩沉淀下来)
- [5. Workflow / Graph / Loop：可控的迭代结构](#5-workflow--graph--loop可控的迭代结构)
- [6. Memory：短期 vs 长期、编码→存储→提取→巩固→反思→遗忘](#6-memory生命周期)
- [7. Prompt Engineering 四要素 + 调优流程](#7-prompt-engineering-四要素--调优流程)
- [8. Loop Engineering：外层反馈循环](#8-loop-engineering外层反馈循环)
- [9. MCP / Function Calling：工具接入标准](#9-mcp--function-calling工具接入标准)
- [10. 实测案例：OpenAI / Anthropic / Stripe / Hashimoto 怎么落地](#10-实测案例一线团队怎么落地)
- [11. 我们项目诊断：6 层架构逐层打分](#11-我们项目诊断6-层架构逐层打分)
- [12. 90 天补全路线](#12-90-天补全路线)

---

## 0. 核心论点

**Agent = Model + Harness**。模型只提供推理和生成，Harness 把状态、工具、反馈、执行环境和安全边界串起来。两者必须一起调优，模型换了 Harness 不动，效果会断崖式下跌。

**Agent 不稳定 90% 不是模型问题**，是 Harness 没搭好：
- 工具描述写歪 → 模型不知道该不该调
- Context 太脏 → 模型在 100K 噪声里抓不到重点（40% 阈值现象）
- Loop 没边界 → 死循环烧 Token
- 状态没持久化 → 重启即失忆
- 验证机制缺位 → AI 写的测试验证 AI 写的代码（"用同一双眼睛检查自己作业"）

**判断标准很简单**：执行路径能不能提前确定。能确定 → Workflow；不能确定 → Agent；两者都有 → Agentic Workflows（全局 Workflow + 局部 Agent 子循环）。

---

## 1. Agent 范式选择

### 1.1 范式全景

| 范式 | 核心思想 | 适用场景 | 代价 |
|------|----------|----------|------|
| **ReAct** | 推理 ↔ 行动交替，边想边做 | 路径不确定、需要证据驱动 | 调试难、Token 烧得多 |
| **Plan-and-Execute** | 先全局规划，再按步骤执行 | 任务长、依赖关系明确 | 动态调整弱 |
| **Reflection** | 让模型检查自己的工作 | 输出质量要求高 | 通常不单独用 |
| **Multi-Agent** | 多角色协作 | 任务天然可拆 | 通信和调试成本翻倍 |
| **Workflow / Graph** | 流程图驱动，LLM 是节点 | 路径可提前确定 | 前期设计成本高 |
| **Agentic Workflows** | 全局 Workflow + 局部 ReAct 嵌套 | 长任务 + 子任务不可预测 | 复杂度高 |

### 1.2 选型决策树

```text
执行路径能提前确定吗？
├── 是 → Workflow（稳定、可观测）
│         ├── 节点需要 LLM？→ 嵌一个 Agent 子循环
│         └── 节点都是确定性逻辑？→ 纯 Workflow
└── 否 → Agent
         ├── 任务很短？→ ReAct
         ├── 任务长且依赖清晰？→ Plan-and-Execute
         ├── 输出质量要求高？→ 叠加 Reflection
         ├── 任务天然可拆多角色？→ Multi-Agent
         └── 局部可预测 + 局部不可预测？→ Agentic Workflows
```

### 1.3 实战建议

> "**先用最简单的方式跑通，再根据实际失败模式决定升级哪一层。** 上来就搞 Multi-Agent、全靠模型动态推理、上下文不做任何管理，踩进去了再爬出来会很费劲。" —— JavaGuide

**我们项目**：booking 流程之前是**硬编码 Plan**（业务调度），目前已经升级到 **Agentic**（LLM 真正接管工具调用），但**没规划 Plan-and-Execute**（全局规划缺失）。详见 §11。

---

## 2. Harness Engineering 六层架构

> **JavaGuide 原话**：决定 Agent 表现上限的，可能不是模型，而是你给模型搭的那套工作环境。
> **实验佐证**：Can.ac 同一个模型，换一套文件编辑接口，编码基准从 6.7% → 68.3%。

### 2.1 六层模型

| 层 | 解决 | 关键设计 | 借鉴案例 |
|----|------|----------|----------|
| **L1 信息边界** | Agent 该知道什么 | 角色 + 目标 + 结构化任务状态 | OpenAI `AGENTS.md`（100 行） |
| **L2 工具系统** | 怎么和外部交互 | 工具描述边界 + 调用时机 + 结果反馈 | Anthropic Skills 渐进式披露 |
| **L3 执行编排** | 多步骤怎么串 | CoT + 条件边 + 工具调度 | Stripe Minions 状态机 |
| **L4 记忆状态** | 长任务怎么管理 | 短期 / 长期分层 + 进度追踪 | Claude Code Memory Tool |
| **L5 评估观测** | 怎么知道做对了 | LLM-as-Judge + 沙箱 + Chrome DevTools | OpenAI Devbox |
| **L6 约束恢复** | 出错怎么办 | 拦截 + 重试 + 回滚 + 降级 + HITL | Anthropic context resets |

### 2.2 落地优先级（来自 OpenAI / Anthropic 实战）

| 优先级 | 行动 | 理由 |
|--------|------|------|
| **P0** | 创建 `AGENTS.md`（持续维护） | 每一行对应一个历史失败案例 |
| **P0** | 写自定义 Linter + 修复指令 | 错误消息自带修复方法 |
| **P0** | 团队知识放进仓库（不进 Slack） | 仓库是可版本化的事实来源 |
| **P1** | 分层管理上下文（`AGENTS.md` 当目录） | 避免超大文件撑爆 40% 阈值 |
| **P1** | 进度文件 + 功能列表 | Agent 不易乱改结构化数据 |
| **P1** | 端到端验证能力（Playwright MCP） | 让 Agent 像用户一样验证 |
| **P2** | Agent 专业化分工 | 携更少无关信息，留在 Smart Zone |
| **P2** | 定期垃圾回收 | 清理速度追上生成速度 |
| **P2** | 可观测性集成 | 把优化从感觉变成可测量 |

### 2.3 上下文利用率 40% 阈值（必须监控）

| 区间 | 占比 | 表现 |
|------|------|------|
| **Smart Zone** | 0-40% | 推理聚焦、工具调用准确 |
| **Dumb Zone** | >40% | 幻觉增多、兜圈子、格式混乱 |

**应对**：
- 监控：每次 LLM 调用前估算 `tokens_used / context_window`
- 阈值告警：>40% 触发压缩 / 分段
- 极端情况：直接 context resets（清窗口 + 交接文档）—— Anthropic 的经验

### 2.4 Harness 当前阶段自检

| 阶段 | 特征 | 工程师角色 |
|------|------|-----------|
| **Level 0** | 无 Harness，纯 Prompt | 手动写代码 |
| **Level 1** | `AGENTS.md` + Linter + 手动测试 | AI 辅助 |
| **Level 2** | CI/CD + 自动化测试 + 进度追踪 | 规划和审查 |
| **Level 3** | 多 Agent + 分层上下文 + 持久化记忆 | 设计环境 |
| **Level 4** | 无人值守并行 + 自修复 | 架构 + 质量把关 |

**我们项目**目前大概在 **Level 1-2 之间**（有 Skill 框架、有 stuck loop 检测、有部分 CI，但缺自动化回放 + 进度追踪）。详见 §11。

---

## 3. Context Engineering：上下文是 Agent 的工作记忆

> **JavaGuide 原话**：Context Engineering 就是 **LLM 的内存管理**。
> 上下文窗口是公共资源，**不是塞得越多，Agent 表现就越好**。

### 3.1 Context vs Prompt

| 维度 | Prompt Engineering | Context Engineering |
|------|--------------------|---------------------|
| 关注点 | 指令本身怎么写 | 窗口里放什么、放多少、什么时候撤 |
| 时间点 | 写提示词时 | **每次 LLM 调用前** |
| 类比 | 告诉厨师菜怎么做 | 给厨师准备厨房 |

**Tobi Lutke 总结**：the art of providing all the context for the task to be **plausibly** solvable by the LLM.

### 3.2 Context Rot（上下文腐化）

**现象**：上下文越长，模型利用上下文的稳定性越差。
**机制**：
- 噪声多 → 模型在大量内容里筛选关键线索变难
- **Lost in the Middle**：模型对开头 / 结尾的信息更敏感，中间容易被忽略
- Attention 分散：每个 Token 都要和其他 Token 算注意力，Token 越多计算和筛选压力越大

**应对**：
- 删掉重复和无关信息
- 把关键约束放到更显眼位置（开头 / 结尾）
- 长文档先切分 / 摘要 / 检索，不要整篇硬塞
- 任务目标、背景、约束、输出要求分块

### 3.3 Context Assembler（每次 LLM 调用前的装配流程）

```python
# 1. 加载系统约束
constraints = load_system_constraints()      # 角色 + 边界 + 权限

# 2. 提取当前目标
goal = extract_current_goal(user_task, session_state)

# 3. RAG 检索证据
evidence = retrieve_rag(goal, business_context)

# 4. 召回历史记忆
memory = recall_memory(goal, session_state)

# 5. 选择工具
tools = select_tools(goal, evidence, memory)

# 6. 压缩历史
history = compact_history(session_state.messages)

# 7. 排序聚合
context = rank([constraints, goal, evidence, memory, tools, history])

# 8. 适配 Token 预算
context = fit_token_budget(context)
```

**两个最关键**：`rank`（决定信息顺序） + `fit_token_budget`（决定哪些压成摘要 / 只留引用）。

### 3.4 预检索 vs Just-in-Time vs 混合

| 策略 | 优点 | 代价 | 适合 |
|------|------|------|------|
| **预检索** | 快、链路稳定 | 易塞入噪声、运行中不灵活 | FAQ、固定知识库 |
| **Just-in-Time** | 上下文干净、证据按需 | 工具调用多、延迟高 | 代码库分析、故障排查 |
| **混合** | 兼顾启动速度和运行时探索 | 需要预算管理 + 工具导航 | 复杂业务 Agent |

**原则**：**确定性高的静态知识预检索，动态发现的信息按需拉取**。

### 3.5 长任务三大武器

| 技术 | 适用场景 | 做法 |
|------|----------|------|
| **Compaction** | 长流程持续对话 | 窗口快满时把历史交给 LLM 摘要，丢冗余工具结果 |
| **Structured Note-taking** | 迭代式开发、多步推进 | 写 `NOTES.md` 记录进度 / 待办 / 已知问题 |
| **Sub-agent** | 复杂研究、并行探索 | 子 Agent 探查详情，主 Agent 只收 1000-2000 Token 摘要 |

### 3.6 Token 预算优先级

| 优先级 | 内容 | 处理 |
|--------|------|------|
| **低（可折叠）** | 早期对话历史 | AI 摘要压缩 |
| **中（可精简）** | RAG 背景、旧工具结果 | 二次裁剪，保留核心 + 可回查引用 |
| **高（固定区）** | System Constraints、当前任务目标、安全边界 | 固定高优先级 |
| **阶段性** | 当前阶段工具描述、Schema、少量关键示例 | 按阶段加载/卸载 |

### 3.7 Context 失败的 5 类兜底

| 失败路径 | 典型表现 | 兜底方案 |
|----------|----------|----------|
| RAG 无结果 | 找不到相关文档 | 降级到关键词检索 / 向用户澄清 |
| 工具超时 | 外部 API 卡住 | 超时 + 重试上限 + 熔断 + 人工接管 |
| 摘要丢失 | 缺异常栈 / 版本号 | 保留 traceId + 原始证据位置 + 关键字段 |
| 记忆污染 | 旧偏好被当当前事实 | 写入前校验、读取后标记时间和可信度 |
| 多工具冲突 | 选错路径 | 用优先级 + 状态机 + 副作用等级约束 |

### 3.8 评估 Context Engineering 的 5 类指标

| 指标 | 看什么 |
|------|--------|
| 任务成功率 | 是否完成、是否需人工补救 |
| 工具质量 | 错选 / 漏调 / 参数错误 / 重复 / 危险操作拦截率 |
| 上下文成本 | 输入 / 输出 Token、缓存命中率、压缩后信息保留比例 |
| 延迟 | 首 Token、端到端、工具等待、p95/p99 |
| 结果质量 | 幻觉率、证据引用准确率、关键字段遗漏率 |

**做法**：先选 20-50 条真实任务轨迹做小评测集，**每次只改一个变量**，改完跑一遍回归。

**我们项目**：评测集为空（详见 §11）。

---

## 4. Skills：把"老员工脑子里的规矩"沉淀下来

> **核心**：Skill 是可被 Agent 发现、按需加载的任务说明。不是替代 Prompt / Function Calling / MCP。

### 4.1 Skill 的定位

```text
用户输入（Prompt）
  ↓
宿主加载可用 Skills 的简短描述（Skill 元数据）
  ↓
模型判断当前任务命中了哪个 Skill（路由）
  ↓
宿主把完整 SKILL.md 加载进来（延迟加载）
  ↓
模型按 Skill 流程调工具 / 读资料 / 写结果
```

### 4.2 SKILL.md 怎么写

**目录结构**：
```text
skill-name/
├── SKILL.md          # 主文件（YAML frontmatter + 正文）
├── scripts/          # 可执行脚本（不加载到上下文）
├── references/       # 参考资料（按需加载）
└── assets/           # 模板和静态文件（按需加载）
```

**元数据规范**：
- `name`：动名词形式（`processing-pdfs`），最多 64 字符
- `description`：说清"做什么 + 什么时候用 + 触发词"
  - ✅ 好：`从 PDF 文件中提取文本和表格、填充表单、合并文档。在处理 PDF 文件或用户提及 PDF、表单、文档提取时使用。`
  - ❌ 差：`我可以帮助您处理 PDF 文件`（无触发条件）

**正文原则**：
1. **不写科普**：Agent 不需要解释 PDF 是什么
2. **写默认值**：`默认使用 pdfplumber 提取文本。如果是扫描版 PDF，需要 OCR，再改用 pdf2image + pytesseract`
3. **写踩坑清单**：`users 表使用软删除。所有正式查询都必须加 WHERE deleted_at IS NULL`
4. **控制长度**：< 500 行（细节拆到 `references/`）
5. **自由度分层**：
   - **低自由度**（迁移 / 部署 / 删文件）：写死命令
   - **中自由度**（有模板）：给模板 + 边界
   - **高自由度**（代码审查）：给检查方向，不写死步骤

### 4.3 渐进式披露（三层模型）

```text
广告层（启动时加载）
  name + description（< 100 Token）
  ↓ 命中
指令层（任务匹配时加载）
  SKILL.md 正文（< 500 行）
  ↓ 引用
资源层（执行时按需加载）
  scripts/ + references/ + assets/
```

**核心**：**不要把所有内容塞进主文件**。能用脚本执行的别放正文；长说明拆到 `references/`。

### 4.4 Skill 路由（数量上来后）

**轻量方案**（几十个 Skill）：
1. **粗召回**：把 name/description/典型 query 向量化，余弦相似度取 top-5
2. **精排**：同时命中 title/description/examples 的优先级更高
3. **兜底**：最高分都很低 → 不选任何 Skill，走默认流程（"不选"比"硬选"更安全）

**冷启动补救**：在元数据加 `triggers` 字段：
```yaml
triggers:
  - "接口卡死了"
  - "频繁 Full GC"
```

### 4.5 工作流 + 反馈循环

复杂 Skill 不能只写一句"先做什么再做什么"，必须把验证点写进流程：

```markdown
## 数据库迁移
运行：python scripts/migrate.py --verify --backup
**不要修改命令，不要添加额外参数。**
如果命令失败，停止执行，并把错误输出返回给用户。
```

**TDD Skill 范例**：
```markdown
### RED - Write Failing Test
### Verify RED - Watch It Fail  ←  MANDATORY. Never skip.
### GREEN - Minimal Code
### REFACTOR - Clean Up
```

### 4.6 写 Skill 8 大坑

| 坑 | 后果 | 改法 |
|----|------|------|
| 把 Skill 当 README 写 | 大量无效信息 | 只写"做什么 + 什么时候用 + 边界" |
| 想做万能助手 | 边界模糊，Agent 纠结 | 拆小（`jvm-analyzer` / `trace-finder` / `k8s-pod-viewer`） |
| 给 Agent 太多选择 | 每次选得不一样 | 默认方案 + 兜底方案 |
| 术语来回换 | Agent 规则飘 | 同概念统一用词 |
| 让 LLM 做确定性工作 | 不稳定 | 格式转换 / 计算 / 批量处理交给脚本 |
| description 写太泛 | 不会被触发 | 写清"做什么 + 触发词" |
| 自由度一刀切 | 高风险任务失控 / 低风险任务变笨 | 按任务风险分层 |
| 没验证点 | Agent 跳过关键步骤 | 把 checklist 写进 SKILL.md |

**第三方 Skill 安全**：审一遍正文 + 脚本 + 参考文件。`SKILL.md` 也是指令，可能夹带不安全操作。

---

## 5. Workflow / Graph / Loop：可控的迭代结构

### 5.1 三者关系

> **Workflow** 是目标与过程，**Graph** 是结构与载体，**Loop** 是图上的控制模式。

```text
"先生成初稿，再审核，不达标就修改，直到达标后输出"
  → 这描述的是 Workflow

"draft → review → revise (回边) → review → exit"
  → 这是 Graph（节点 + 边 + 共享状态）

"review 评分 < 80 且 iteration < 3 → revise"
  → 这是 Loop（条件驱动循环）
```

### 5.2 Graph 三元素

**Node（节点）**：执行单元。**只做一件事**。可以调 LLM、调工具、纯代码逻辑。

**Edge（边）**：控制流
- **顺序边**：固定顺序
- **条件边**：根据 State 在预定义候选路径中选择（`addConditionalEdges()`）
- **动态路由**：候选节点在运行时确定（LangGraph `Send` API）
- **循环边**：回边，节点回到自身或前序节点
- **终止边**：流程结束
- **并行边**：一个节点分发到多个后续节点

**State（状态）**：节点间共享的"工作记忆"。**键值对数据结构**（`Map<String, Object>` / `dict`）。

**State 更新策略**：
- **覆盖（Replace）**：新值替换旧值（单值字段）→ `ReplaceStrategy`
- **追加（Append）**：新值加到列表（累积型字段，如 messages）→ `AppendStrategy`
- **自定义 Reducer**：如 `add_messages` 按 ID 追加或更新

**常见字段**：`input` / `messages` / `retrieval_result` / `tool_result` / `llm_response` / `intermediate_steps` / `next_step` / `output`

### 5.3 Loop 设计三要素

**可靠的 Loop 一定包含**：
1. **继续条件**：为什么还要再来一轮
2. **退出条件**：什么时候已经足够好
3. **安全边界**：最大轮次 / 超时 / 预算 / 熔断

> 没有这些约束，Loop 会从"自我修正"变成"无限打转"。

**两种循环**：
- **固定次数循环**（`for`）：最多重试 3 次
- **条件驱动循环**（`while`）：只要评分 < 80，就继续

**实际开发中两者必须同时用**：LLM 可能一直生成不合格内容，需要固定次数兜底。

**嵌套循环**：外层"质量迭代"、内层"工具重试"（指数退避）。两层独立退出条件 + 安全边界。

### 5.4 错误处理四类

| 错误类型 | 例子 | 策略 |
|----------|------|------|
| **瞬时错误** | 网络超时、API 限流 | 指数退避重试（1s/2s/4s，最多 5 次） |
| **LLM 可恢复错误** | 工具调用失败、输出格式异常 | 把错误塞 State，循环回去让 LLM 调整 |
| **用户可修复错误** | 缺必要信息、指令不明确 | `interruptBefore` 暂停等人工输入 |
| **意外错误** | 未知异常 | 让异常冒泡，交给开发者调试 |

### 5.5 工作流落地 5 大坑

| 坑 | 表现 | 改法 |
|----|------|------|
| State 粒度太粗 | 谁改了哪个字段不好查 | 按业务含义分块（输入 / 当前结果 / 审核结论 / 流程控制） |
| State 粒度太细 | 节点要拼来拼去 | 同上 |
| 循环终止条件不明确 | 无限重试 | 写清最大轮次 + 评分阈值 + 成本上限 + 降级路径 |
| 错误处理靠外层 try-catch 吞掉 | 失败路径不可见 | 在图上明确边：重试 / 降级 / 转人工 / 输出"当前最优+错误说明" |
| Token 成本失控 | Loop 越跑越贵 | 哪些必须大模型 / 哪些可以代码；先粗筛再精修；"足够好"就退出 |

### 5.6 AI 工作流的安全风险

| 风险 | 描述 | 防御 |
|------|------|------|
| **提示注入的级联影响** | 恶意输入覆盖 system prompt，逐节点放大 | 输入过滤、严格分隔系统/用户提示、LLM 输出做安全检测 |
| **工具调用权限越界** | 删除/发送未授权 | 最小权限、高危操作 HITL |
| **输出内容注入** | LLM 输出进入下游系统 | 进入数据库/前端/Shell 前必须校验 |
| **State 污染** | 恶意输入改 next_node 跳过审核 | 路由控制字段白名单校验 |
| **Loop 放大攻击** | 构造让 ReviewNode 永远低分 | 除 iteration_count 上限外，加 Token 预算作为独立安全边界 |

---

## 6. Memory：生命周期

### 6.1 短期 vs 长期

| 类型 | 范围 | 例子 |
|------|------|------|
| **短期记忆** | Session 内 | 滑动窗口、对话历史 |
| **长期记忆** | 跨 Session | 用户偏好、习惯、画像 |

### 6.2 长期记忆 ≠ RAG

- **RAG**：共享知识源（公司规章、产品文档），不个性化
- **长期记忆**：用户专属偏好

**我们项目**：RAG 做对了（产品知识），长期记忆**写了一半**——`long_term_memory.py` 写了 `extract_facts_with_llm`，但**没自动从 chat 提取**，也**没自动注入 system prompt**。详见 §11。

### 6.3 记忆生命周期 6 阶段

```text
编码 → 存储 → 提取 → 巩固 → 反思 → 遗忘
```

| 阶段 | 作用 | 我们的状态 |
|------|------|-----------|
| **编码** | 用 LLM 从对话里提取 fact | ✅ 写了 `extract_facts_with_llm`（没自动触发） |
| **存储** | 存到 user_profiles | ✅ |
| **提取** | 按需检索相关 fact | ❌ **没读取** |
| **巩固** | 短期转长期（高频访问 → 永久） | ❌ |
| **反思** | 提取经验、合并相似 fact | ⚠️ `merge_similar_facts` 写了，没自动调度 |
| **遗忘** | 淘汰低价值 fact | ❌ |

### 6.4 记忆操作的高级特性

借鉴 Mem0 / Letta：
- **删除**：`delete_user_fact(user_id, fact_key)` — 撤回 / GDPR
- **去重**：`merge_similar_facts(threshold=0.92)` — 合并同 key 相似 fact
- **时间窗口**：`get_recent_facts(user_id, days=30)`
- **监控**：`fact_count_per_user()` — 防膨胀

我们项目已经有 `long_term_memory_v2.py` 实现上述 4 项，**但都是手动调用，没编排进主流程**。

---

## 7. Prompt Engineering 四要素 + 调优流程

### 7.1 四要素框架

| 要素 | 作用 | 例子 |
|------|------|------|
| **Role** | 告诉模型该用哪个领域知识 | "你是一位 10 年经验的 Java 架构师" |
| **Task** | 说明要完成什么动作 | "请评审以下代码的性能问题" |
| **Context** | 补充业务背景 | "当前线上 QPS 2000，响应时间超 500ms" |
| **Format** | 规定输出格式 | "输出 JSON，包含 bottleneck/solution 字段" |

**位置原则**：**Role 放开头**（模型对开头敏感），**Format 放结尾**。Lost in the Middle 现象。

### 7.2 六大核心技巧

1. **角色扮演**：角色越具体越稳。"你是 AI" < "你是一位专注于性能优化的 Java 架构师"
2. **CoT 思维链**：
   - Zero-shot："请给出关键步骤后再回答"
   - 引导式：在回答前先检查 3 个问题
   - XML 标签：`<checks>` + `<answer>` 分开
3. **Few-shot**：1-3 个多样化示例，不是堆 edge case
4. **任务分解**：把复杂任务拆成子任务
5. **结构化输出**：JSON Schema / Function Calling
6. **XML 标签 + 预填充**：用 `<context>` `<rules>` 等标签分隔

### 7.3 调优流程

```text
1. 准备样例（10-30 条覆盖正常/边缘/异常）
2. 固定变量（模型/Temperature/System Prompt/检索材料）
3. 记录指标（格式合规率、事实错误率、字段缺失率、人工修改次数）
4. 单点修改（每次只改一个变量）
5. 回归测试（保留失败样例，定期回放）
```

> **现实**：一条最终上线的 Prompt 往往要 5-10 轮调整。

### 7.4 写 Prompt 两个极端

| 极端 | 表现 | 后果 |
|------|------|------|
| **过度设计** | 把大量 if-else 塞进 Prompt | 长且脆弱，边缘情况照样跑偏 |
| **过度抽象** | "你要做一个有帮助的助手" | 模型不停追问 / 偏题 |

**Goldilocks Zone**：具体到能引导行为，抽象到能覆盖常见变化。Anthropic 叫 Calibrating the system prompt——**System Prompt 应该是持续调校的参数**。

---

## 8. Loop Engineering：外层反馈循环

### 8.1 核心论点

> **新瓶装旧酒**：Agent Loop、Workflow Graph、Context Engineering、Skills、MCP、CI、测试验证——这些 JavaGuide 之前都聊过。Loop Engineering 是把它们重新摆到代码 Agent 周围。

**Loop = 内层 Agent Loop（推理-行动-观察）+ 外层 Engineering Loop（调度-验证-记录）**：

| 层级 | 谁在循环 | 每轮做什么 | 典型停止 |
|------|----------|------------|----------|
| **内层 Agent Loop** | Agent 自己 | 思考、调用工具、观察、继续 | 不再需要工具 |
| **外层 Engineering Loop** | 调度系统 / 人写的流程 | 唤醒、分配任务、验证、记录 | 达成目标 / 超预算 / 失败转人工 |

### 8.2 Loop 七要素

1. **触发**：谁来启动这轮（手动 / 定时 / CI 失败 / PR 创建 / 事件）
2. **目标**：什么状态算完成（测试通过 / 覆盖率达标 / 截图对齐）
3. **上下文**：每轮要看哪些文件 / 规则 / 历史 / 工具结果
4. **行动**：能改代码 / 跑测试 / 查 GitHub / 读日志 / 发 PR，还是只能输出建议
5. **观察**：怎么知道刚才做对了（测试输出 / lint / 截图 / 评论）
6. **状态**：写到外部文件 / Issue / 卡片，不能只靠当前对话
7. **停止**：什么时候退出 / 转人工 / 因为预算耗尽停

### 8.3 Loop 四类

| 类型 | 触发 | 适合任务 | 代表工具 |
|------|------|----------|----------|
| **时间驱动** | 每 N 分钟、每天、每周 | PR babysit、CI 检查、日志巡检 | `/loop`、cron |
| **事件驱动** | CI 失败、Issue 创建、PR 更新 | 故障分拣、评论处理、告警摘要 | GitHub Actions、Webhook |
| **目标驱动** | 上一轮结束检查目标 | 修测试、迁移 API、补覆盖率 | `/goal`、Stop hook |
| **人工审批** | 关键动作前确认 | 发布、权限变更 | approval gate、draft PR |

### 8.4 典型 Loop 示例（CI 排查）

```text
1. 触发器：每天 9 点 / CI 失败时
2. 输入：最近一次 CI 失败、相关 PR、最近提交、失败测试日志
3. 上下文：AGENTS.md + ci-triage Skill + 相关模块文件
4. 行动：分析失败原因（环境抖动 / 测试不稳定 / 代码回归 / 依赖问题）
5. 验证：能复现就跑最小测试集；不能复现就保留证据
6. 状态：结论写入 TODO.md / GitHub Issue / Linear 卡片
7. 输出：简短报告，标 "可自动修复" / "需负责人确认" / "疑似偶发"
8. 停止：不直接推送代码，不改生产配置，不连续重试 > 3 次
```

### 8.5 什么场景值得做 Loop

**适合**：
- CI 失败初步排查（有日志 / 测试结果 / 明确失败信号）
- 依赖升级（独立分支 + 测试验证）
- 测试覆盖率补齐（可量化）
- 文档同步（diff → 文档 → 人工 review）
- 大规模机械迁移（CommonJS → ESM / 旧组件 API 替换）
- PR / Issue 分拣

**不适合**：
- 目标很虚（"让产品体验更好"）
- 验证信号弱（Agent 自己说"我觉得可以了"）
- 做错影响大（生产数据库写、权限系统、支付链路）
- 强依赖人的审美（品牌文案、复杂取舍）
- 没有测试 / 日志 / 回滚方式的老项目大改

> **金句**：你自己都说不清怎么验收，就别急着 loop。先把目标拆小，把验收标准写出来。

### 8.6 Claude Code 的 /loop / /goal 经验

- **`/loop`**：session-scoped 临时调度，**任务只在该 session 跑且空闲时触发**；最多 7 天自动过期
  - 跨机器、跨重启、长期稳定 → 考虑 Routines / GitHub Actions / 自建调度
- **`/goal`**：每轮结束后由独立小模型基于已有证据判断条件是否满足
  - 适合"修测试 / 迁移 API / 补覆盖率"
- **习惯**：跑 `/loop` 前先收紧权限 + 写清轮询目标和停止条件；跑 `/goal` 前把完成条件写成可验证结果

---

## 9. MCP / Function Calling：工具接入标准

### 9.1 核心区分

> **JSON Schema 是数据格式，MCP 是通信协议层。**

| 概念 | 解决什么 |
|------|----------|
| **Function Calling Schema** | 数据格式（工具长什么样） |
| **MCP** | 通信协议（工具怎么接入宿主） |
| **Skills** | 经验包（怎么调 + 什么时候不调） |
| **Prompt** | 用户说什么 |
| **Toolkit（黑盒）** | 把多个原子工具封装成高阶工具 |

### 9.2 Function Calling Schema 要点

**Schema 写得好不好，直接决定 Agent 选不选这个工具**。

```json
{
  "type": "function",
  "function": {
    "name": "query_slow_sql",
    "description": "查指定微服务在特定时间段的慢 SQL 日志。服务响应慢、数据库超时、CPU 飙升的时候用。如果用户问的是网络或内存问题，别调这个。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_name": {"type": "string", "description": "服务名，比如 user-service、order-service"},
        "time_range": {"type": "string", "description": "时间范围 HH:MM-HH:MM"},
        "threshold_ms": {"type": "integer", "description": "慢 SQL 阈值（毫秒），默认 1000"}
      },
      "required": ["service_name", "time_range"]
    }
  }
}
```

**好 description 要回答**：
- 什么时候该调？
- 什么时候不该调？
- 参数格式 + 示例
- 错误码 / 边界值

### 9.3 MCP 三类原语

| 原语 | 作用 | 例子 |
|------|------|------|
| **Tools** | LLM 主动调用的函数 | 查数据库、发邮件、执行代码 |
| **Resources** | Agent 按需读取的只读数据 | 本地文件、数据库记录、日志流 |
| **Prompts** | 可复用的提示词模板 | 代码审查模板、故障报告模板 |

**易错点**：MCP Server 对外暴露工具时，内部还是用 JSON Schema 描述参数。**JSON Schema 是数据格式，MCP 是通信协议层**。

### 9.4 MCP 接入后的新风险

工具一旦暴露给 Agent，不只是能力入口，**也是副作用入口**：
- 读文件、查数据库、发请求、改配置 → 边界没卡住，排查痛苦
- **权限**：最小权限原则
- **审计**：所有调用留痕
- **限流**：防 Agent 循环调用昂贵 API
- **脱敏**：查询结果中的敏感信息
- **HITL**：高危操作（删除、发送）必须人工确认

**无人值守 Loop 拿到过大的写权限** → 可能改错数据 / 发错消息 / 重复调用昂贵接口 / 被提示词注入诱导读不该读的文件。

### 9.5 Skills 路由的对比

| 维度 | RAG | Skills 路由 |
|------|-----|-------------|
| 目标 | 多召回几段，模型生成时过滤 | **最怕选错**（选错整条执行路径跑偏） |
| 规模 | 万级文档 | 几十到几百个 |
| 召回 | 宽松 | 严格 |
| 冷启动 | 文档自带内容 | 靠 `triggers` 字段喂样本 |

---

## 10. 实测案例：一线团队怎么落地

### 10.1 OpenAI：3 人 5 个月 100 万行代码

**指标**：
- 团队：3 → 7 人
- 持续：5 个月
- 代码：约 100 万行，0 行手写
- PR：约 1500 个，3.5 个/人/天
- 效率：约 10 倍

**核心做法**：

1. **AGENTS.md 当目录，不当手册**
   - 约 100 行，只做导航
   - 详细规则在 `docs/` 子目录
   - 渐进式披露

2. **架构约束要靠工具执行**
   - 分层：`Types → Config → Repo → Service → Runtime → UI`
   - 自定义 Linter + 结构测试
   - 错误消息**自带修复方法**
   - **金句**：If it cannot be enforced mechanically, agents will deviate.

3. **可观测性给 Agent 看**
   - Chrome DevTools Protocol 接进 Agent 运行时
   - Agent 可抓 DOM 快照 + 截图
   - 日志 / 指标 / 链路追踪暴露给 Agent
   - "把启动时间降到 800ms 以下" → 可自我测量、自我验证的目标

4. **熵管理**
   - 早期每周五花 20% 时间手动清理
   - 后期：后台 Agent 定期扫描文档不一致 / 架构违规 / 冗余代码，自动提交清理 PR

5. **仓库作为事实来源**
   - 不进 Slack、不进 Google Docs（对 Agent 不稳定）
   - 团队知识作为版本控制制品放进仓库

### 10.2 Anthropic：从上下文焦虑到三智能体架构

**Carlini 用 16 个 Agent 写 C 编译器**：
- 持续：约 2 周
- 并行：16 个 Claude Opus 实例
- 会话：约 2000 个
- 产出：10 万行 Rust 代码
- 测试：GCC torture test 99% 通过
- 编译：PostgreSQL、Redis、FFmpeg、CPython、Linux 6.9 Kernel 等 150+
- 成本：约 2 万美元

**Harness 细节**：
- **日志不打到控制台**，全部写进文件，`ERROR: [reason]` 格式（grep 友好，主动减少上下文污染）
- **测试不全跑**：每个 Agent 只跑随机 1-10% 子集；同一次运行确定；跨 VM 随机
- **角色专业化**：核心 / 去重 / 性能优化 / 代码质量 / 文档

**金句**："我必须不断提醒自己，我是在为 Claude 写这个测试框架，不是为自己写。"

**Anthropic 三智能体架构**（受 GAN 启发）：

```ebnf
Planner（规划者）→ Generator（执行者）⇄ Evaluator（评估者）
```

- Planner：把 1-4 句话产品描述扩展成完整规格，要求"在范围上要大胆"
- Generator：按功能一个个做 Sprint
- Evaluator：用 Playwright MCP 实际点击运行中的应用，按设计 / 功能 / 视觉 / 代码质量打分

**前端设计评分**：设计质量 + 原创性的权重**故意调得比功能性 + 代码质量更高**——逼模型往更难的方向走。

**Context Resets（解决 Sonnet 4.5 上下文焦虑）**：
- 上下文快满时，先结构化提取当前任务状态 / 已完成 / 待办
- 启动新 Agent，把交接文档给它
- 新 Agent 从干净状态继续

**两种配置成本对比**：

| 配置 | 耗时 | 花费 | 效果 |
|------|------|------|------|
| Solo Harness（单 Agent + 最少工具） | 20 分钟 | $9 | 跑不起来的半成品 |
| Full Harness（三 Agent + 完整工具链） | 6 小时 | $200 | 完整可用应用 |

**金句**：Every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing.

**结论**：模型变强后，Harness 要定期简化。Sonnet 4.5 → Opus 4.6 后，Sprint 机制可移除，Evaluator 改为最后只检查一次。

### 10.3 Stripe：每周 1300+ PR 的无人值守

**Minions 系统**：
- 开发者发 Slack 消息 → Agent 写代码 → 跑 CI → 提 PR → 人审查
- 每周 1300+ 完全无人值守 PR

**核心组件**：

| 组件 | 作用 | 关键设计 |
|------|------|----------|
| Devbox | 开发环境 | AWS EC2 预装 + 预热池，启动约 10 秒，"牲口不是宠物" |
| 编排状态机 | 流程控制 | 混合确定性节点（lint/push）+ Agent 节点（实现/修 CI） |
| Toolshed MCP | 工具服务 | 集中式 MCP，近 500 个工具，每个 Minion 拿筛选子集 |
| 反馈回路 | 质量保障 | Pre-push hook 秒级修 lint；推送后最多 2 轮 CI，覆盖 300 万+ 测试 |

**金句**：What's good for humans is good for agents. 过去为人类工程师投入的 Devbox / 工具链 / 开发者体验，在 Agent 上直接产生回报。

### 10.4 Mitchell Hashimoto：一个人的 Harness 工程学

**坚持单 Agent 深度参与**，明确说："我不打算跑多个 Agent，也不想跑。"

**6 步法**：

| 步骤 | 名称 | 做法 |
|------|------|------|
| 1 | 放弃聊天模式 | Agent 在能读文件 / 跑程序 / 发 HTTP 的环境里直接干活 |
| 2 | 复现自己的工作 | 每件事做两次，一次自己做，一次让 Agent 做（"痛苦至极"） |
| 3 | 下班前启动 Agent | 每天最后 30 分钟布置任务（深度调研 / 模糊探索 / Issue 分拣） |
| 4 | 外包确定性任务 | 挑 Agent 几乎一定能做好的后台跑，建议关桌面通知 |
| 5 | 工程化 Harness | 每次犯错，工程化一个方案，让它以后不再犯 |
| 6 | 始终有 Agent 在跑 | 目标 10-20% 工作时间有后台 Agent |

**Ghostty 的 `AGENTS.md`**：每一行对应一个历史失败案例。**持续积累的防错系统**。

### 10.5 5 个公开案例的共性

| 共性 | 表现 |
|------|------|
| **上下文污染** | Sonnet 4.5 上下文快满时草草收尾 |
| **代码熵积累** | 每周 20% 时间手动清理 |
| **工具调用可靠性** | 工具描述错 → 模型选错 |
| **架构约束机械化** | Linter + 结构测试 |
| **可观测性暴露给 Agent** | Chrome DevTools / 日志 / 指标 |

**棕地项目改造是最大挑战**：
- 公开成功案例基本都是**绿地项目**
- 10 年代码库 / 无明确架构约束 / 到处技术债 → 接入 Harness 难 10 倍
- 类比：在从没用过静态分析的代码库上跑静态分析
- **Ambient Affordances**：环境本身的结构特性（类型系统 / 模块边界 / 框架抽象）影响 Harness 能做到什么程度

**AI 生成的测试验证 AI 生成的代码** = "用同一双眼睛检查自己的作业"（Böckeler 批评）

### 10.6 Harness 该做厚还是做薄

> **场景决定**。通用产品更追求最小化（Manus 五次重写越做越简单），特定产品可以高度定制（OpenAI 五个月越做越复杂）。**模型变强后，已有 Harness 也应该定期简化**（Anthropic 验证过）。

---

## 11. 我们项目诊断：6 层架构逐层打分

> 总分（满分 60）：**24/60（40%）**——具备基础能力，但严重缺反馈回路和约束层。

### 11.1 L1 信息边界层：8/10 ✅

| 维度 | 状态 | 证据 |
|------|------|------|
| 角色定义 | ✅ | `_HAIR_SYSTEM_PROMPT` 明确身份 + 能力边界 |
| 目标约束 | ✅ | 知识 / 预约分流到不同 Agent |
| 信息裁剪 | ⚠️ | 部分做了（按 audience 隔离），但 history 全量传 |

**改进**：写 `AGENTS.md`（JavaGuide 强烈推荐），把分散的 system prompt 收敛。

### 11.2 L2 工具系统层：5/10 ⚠️

| 维度 | 状态 | 证据 |
|------|------|------|
| 工具注册 | ✅ | `app/core/tools/order_tools.py` + `tool_registry.py` |
| 工具描述 | ⚠️ | 工具 description 写得**较简单**，没强调"什么时候不该调" |
| 渐进式披露 | ❌ | Skills 框架写了（`app/core/skill.py`），**但 chat 端点没用 skill middleware** |
| MCP 接入 | ❌ | 完全没有 MCP |
| 工具调用监控 | ⚠️ | 有 `tool_repeat_count` 检测（StuckLoopDetector） |
| 工具结果裁剪 | ⚠️ | `RERANK_SAFETY_MAX_CHARS = 8000` 有，但没在 LLM 调用前裁剪 |

**改进**：
1. 给所有 6 个 booking 工具 + `search_hair_knowledge` 写详细 description（使用场景 + 反例 + 参数示例）
2. 把 `app/core/skill.py` 的 SkillRegistry **真的接进 chat 端点**（按 query 路由 + 渐进式披露）
3. 工具结果超长时**先摘要再入上下文**

### 11.3 L3 执行编排层：4/10 ⚠️

| 维度 | 状态 | 证据 |
|------|------|------|
| ReAct 循环 | ✅ | AgentScope 2.0 Agent 接管 booking 流程 |
| Plan-and-Execute | ❌ | 没显式规划阶段 |
| 状态机 | ⚠️ | `_handle_booking_flow` 是硬编码分支，**不是图结构** |
| 条件边 | ⚠️ | 写在 Python if-else 里 |
| 错误恢复 | ❌ | 工具失败直接报错给用户 |
| Graph 抽象 | ❌ | 没有 Node/Edge/State 显式建模 |

**改进**：
1. 引入 LangGraph 或自研轻量图引擎
2. 关键流程改成显式状态机：
   ```
   idle → checkin_branch → checkin_stylist → checkin_service → 
   checkin_datetime → checkin_phone → checkin_name → confirm
   ```
3. 工具失败塞回 State，**让 LLM 自己决定**重试 / 降级 / 转人工

### 11.4 L4 记忆与状态层：6/10 ⚠️

| 维度 | 状态 | 证据 |
|------|------|------|
| 短期记忆 | ✅ | `chat_messages` 表 + Redis 缓存 |
| 长期记忆存储 | ✅ | `user_profiles` 表 + `long_term_memory_v2.py` |
| 长期记忆提取 | ⚠️ | `extract_facts_with_llm` 写了，**没自动从 chat 触发** |
| 长期记忆注入 | ❌ | **`memory_hint` 没注入 system prompt** |
| 巩固 / 反思 / 遗忘 | ⚠️ | `merge_similar_facts` 写了，**没自动调度** |
| 状态持久化（Agent） | ⚠️ | `agent_state_store.py` 写了，但**没在 chat 端点 save/load** |
| 进度文件 | ❌ | 没 NOTES.md / TODO.md 机制 |

**改进**：
1. **关键**：在 chat 端点 end-of-turn 自动调 `extract_and_save_facts_v2`
2. **关键**：下轮 chat 开始时把 `get_recent_facts(user_id, days=30)` 注入 system prompt
3. `agent_state_store` 接入 chat（每次 save 到 session，重启可恢复）
4. 引入 `NOTES.md` 模式（长任务用）

### 11.5 L5 评估与观测层：1/10 ❌

| 维度 | 状态 | 证据 |
|------|------|------|
| `/metrics` 端点 | ⚠️ | `metrics.py` 装了 prometheus_client，**没暴露端点** |
| 任务成功率 | ❌ | 0 指标 |
| 工具质量 | ⚠️ | `tool_repeat_count` 有（不是成功率） |
| 上下文成本 | ❌ | 没统计 input/output Token |
| 延迟 | ❌ | 没 p95/p99 |
| 幻觉率 / 引用准确率 | ❌ | 0 |
| 评测集 | ❌ | `eval_set.py` / `eval_set_en.py` 写了，**没在 CI 跑** |
| RAGAS 评估 | ⚠️ | `ragas_runner.py` 写了（4 维），**没自动跑** |
| 失败样本沉淀 | ❌ | 0 |

**改进**（P0）：
1. 暴露 `/metrics`（参考 JavaGuide 5 类指标）
2. 写 20-50 条真实任务评测集（JavaGuide 强烈推荐）
3. 接入 RAGAS 跑回归
4. 失败样本自动沉淀到 `failed_cases.jsonl`

### 11.6 L6 约束、校验与恢复层：0/10 ❌ **最大短板**

| 维度 | 状态 | 证据 |
|------|------|------|
| Linter / 结构测试 | ❌ | 完全没有 |
| 输入过滤 | ⚠️ | `safety_filter` 有（敏感词），但没注入检测 |
| 提示注入防御 | ❌ | 用户输入直接进 LLM |
| 工具权限边界 | ❌ | 工具可写 DB / 发消息，**无最小权限** |
| 高危操作 HITL | ❌ | `hitl.py` 写了，**没接入 booking flow** |
| 熔断 | ✅ | `model_gateway.py` 用 `pybreaker` |
| 重试 | ✅ | 指数退避 |
| 降级 | ✅ | FallbackStrategy（cache / default / empty） |
| Context Resets | ❌ | 超过 40% 阈值怎么办？没机制 |
| Loop 边界 | ⚠️ | `StuckLoopDetector` 有（3 次 break），但没在图层面建模 |

**改进**（P0）：
1. 写自定义 Linter（OpenAI 经验）：错误消息自带修复方法
2. **HITL 必须接入 booking flow**（商户取消 / 改时间 / 退款都需人工确认）
3. Context 利用率监控（>40% 触发压缩 / context resets）
4. 工具权限分级（读 / 写 / 发 / 删，每级独立授权）
5. 提示注入检测（用户输入先过 safety_filter 再进 LLM）

### 11.7 综合评分

| 层 | 分 | 状态 |
|----|-----|------|
| L1 信息边界 | 8/10 | ✅ 良好 |
| L2 工具系统 | 5/10 | ⚠️ 描述不细、Skills 未启用 |
| L3 执行编排 | 4/10 | ⚠️ 缺图结构、缺 Plan |
| L4 记忆状态 | 6/10 | ⚠️ 写一半，没自动注入 |
| L5 评估观测 | 1/10 | ❌ 几乎为 0 |
| L6 约束恢复 | 0/10 | ❌ **最大短板** |
| **合计** | **24/60** | **40%** |

**阶段定位**：**Level 1 → Level 2 过渡期**（基础约束建立中，但缺反馈回路）

---

## 12. 90 天补全路线

> **核心原则**：**先把 Agent 能力本身做完整**（L1-L4 + L6 核心），再补反馈回路（L5）。
> 评测 / RAGAS / 失败样本沉淀 → **Phase 2** 才做，因为没有可评测的对象。

### Phase 1（P0 - 30 天，补全 Agent 能力）

| 任务 | 工期 | 解决 | JavaGuide 对应 |
|------|------|------|---------------|
| **写 AGENTS.md**（项目级 Harness 文档） | 1 天 | L1 | OpenAI 实践 §10.1 |
| **工具描述升级**（6 个 booking + 检索，描述边界 + 反例） | 1 天 | L2 | MCP §9.2 |
| **Skills 真接入 chat 端点**（skill middleware 路由 + 注入） | 3 天 | L2 | Skills §4 |
| **booking 流程改图结构**（LangGraph 或自研 StateGraph） | 5 天 | L3 | Graph §5.2 |
| **Plan-and-Execute 模式**（复杂任务先规划再执行） | 3 天 | L3 | Plan-and-Execute §1.1 |
| **LTM 自动注入 system prompt**（下轮 chat 开始时拉取） | 2 天 | L4 | 记忆生命周期 §6.3 |
| **end-of-turn 自动提取 fact**（每轮对话结束自动 LTM） | 1 天 | L4 | 编码阶段 §6.3 |
| **Agent 状态持久化**（`agent_state_store` 接入 chat） | 2 天 | L4 | 状态持久化 |
| **NOTES.md 机制**（长任务外部笔记） | 2 天 | L4 | Note-taking §3.5 |
| **工具权限分级**（读/写/发/删，每级独立授权） | 2 天 | L6 | 安全风险 §5.6 |
| **Context 利用率监控**（>40% 告警） | 2 天 | L6 | 40% 阈值 §2.3 |
| **Prompt 调优流程跑通一次**（找一个真实 case 调通 4 要素） | 2 天 | L7 | 调优流程 §7.3 |

**Phase 1 目标**：Agent 能力完整——能可靠执行 booking / knowledge 两条主流程，能记住用户偏好，复杂任务有图结构支撑，高风险操作有权限边界。

### Phase 2（P1 - 30 天，建反馈回路）

| 任务 | 工期 | 解决 | JavaGuide 对应 |
|------|------|------|---------------|
| **HITL 接入 booking flow**（3 个高危操作） | 3 天 | L6 | 错误处理 §5.4 |
| **提示注入检测**（输入过滤 + 输出过滤） | 2 天 | L6 | 安全风险 §5.6 |
| **Context Resets**（>40% 触发清窗口 + 交接） | 2 天 | L4 | Anthropic 实践 §10.2 |
| **Linter 起步**（自定义检查 + 修复提示） | 2 天 | L6 | OpenAI 实践 §10.1 |
| **暴露 /metrics 端点** + 5 类指标 | 2 天 | L5 | Context Engineering §3.8 |
| **写 30 条评测集** + RAGAS 自动跑 | 3 天 | L5 | 调优流程 §7.3 |
| **失败样本自动沉淀** | 1 天 | L5 | 失败样本驱动 |
| **失败样本回放 CI**（改完自动跑评测集） | 2 天 | L5 | Loop Engineering §8 |
| **Sub-agent 模式**（检索隔离，主 Agent 拿摘要） | 3 天 | L3 | Sub-agent §3.5 |
| **Reflection 叠加**（生成后让另一个 LLM 评分） | 2 天 | L3 | Reflection §1.1 |

**Phase 2 目标**：能闭环——有观测、有评测、有失败样本沉淀、有自动回放。

### Phase 3（P2 - 30 天，升华）

| 任务 | 工期 | 解决 | JavaGuide 对应 |
|------|------|------|---------------|
| **MCP Server 接入**（暴露我们的工具给外部 Agent） | 5 天 | L2 | MCP §9 |
| **Multi-Agent 编排**（knowledge + booking + casual 三个 sub-agent） | 5 天 | L3 | Multi-Agent §1.1 |
| **Compaction 长任务压缩**（窗口快满时 LLM 摘要历史） | 2 天 | L4 | Context Engineering §3.5 |
| **自动巩固 / 遗忘**（fact 访问频次 → 转长期 / 淘汰低价值） | 2 天 | L4 | 记忆生命周期 §6.3 |
| **外层 Loop Engineering**（CI 排查 / 文档同步 Loop） | 3 天 | 整体 | Loop Engineering §8 |
| **Harness 阶段自检**（升到 Level 3） | 1 天 | - | §2.4 |

**Phase 3 目标**：从单项目 Agent 升级为可对外服务、可被其他 Agent 调用的能力平台。

### 12.4 关键指标（90 天后目标）

| 维度 | 当前 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|------|------|--------------|--------------|--------------|
| L1 信息边界 | 8/10 | **9/10** | 9/10 | 9/10 |
| L2 工具系统 | 5/10 | **9/10** | 9/10 | **9.5/10**（+MCP） |
| L3 执行编排 | 4/10 | **8/10** | **9/10** | 9.5/10 |
| L4 记忆状态 | 6/10 | **8.5/10** | **9/10** | 9.5/10 |
| L5 评估观测 | 1/10 | 1/10 | **7/10** | 8/10 |
| L6 约束恢复 | 0/10 | **4/10** | **8/10** | 9/10 |
| **合计** | **24/60** | **39.5/60 (66%)** | **51/60 (85%)** | **54.5/60 (91%)** |
| Harness 阶段 | Level 1-2 | **Level 2 稳定** | **Level 2-3** | **Level 3** |

**核心区分**：
- **Phase 1 关心"Agent 做不做得到"**（能力）
- **Phase 2 关心"Agent 做得好不好"**（评估）
- **Phase 3 关心"Agent 能不能被用"**（开放）

---

## 📌 总结：我们到底缺什么

把 JavaGuide 9 篇 agent 文档的核心方法论压缩到一张表，对照我们项目：

| 维度 | JavaGuide 核心 | 我们现状 | 差距 |
|------|----------------|----------|------|
| **范式选择** | 先 Workflow 后 Agent | 用了 ReAct（booking） | 缺 Plan-and-Execute / Agentic Workflows |
| **Harness L1 信息边界** | `AGENTS.md` 当目录 | system prompt 散落 | 没 `AGENTS.md` |
| **Harness L2 工具系统** | 工具描述先讲边界 + Skills 渐进披露 | 工具能调、描述简单 | Skills **写了不用** |
| **Harness L3 执行编排** | Graph + State + 可控 Loop | 硬编码 if-else | **没图结构** |
| **Harness L4 记忆状态** | 6 阶段生命周期 | 写了一半 | **没自动注入** |
| **Harness L5 评估观测** | 评测集 + RAGAS + 失败样本 | 0 | **最薄弱** |
| **Harness L6 约束恢复** | Linter + HITL + Context Resets | 熔断有，HITL 没接 | **最大短板** |
| **Context Engineering** | 40% 阈值 + 三大武器 | compaction 部分 | 缺监控 + Note-taking + Sub-agent |
| **Skills** | SKILL.md + 渐进式披露 + 路由 | 4 个内置 Skill | **没启用** |
| **Workflow / Graph / Loop** | 三要素（继续/退出/边界） | 边界只到 stuck | 缺图结构 + 安全边界 |
| **Memory 生命周期** | 编码→存储→提取→巩固→反思→遗忘 | 只到存储 | 缺 5 个阶段 |
| **Prompt Engineering** | 4 要素 + 调优流程 | 4 要素部分 | **缺评测** |
| **Loop Engineering** | 7 要素 + 4 类循环 | 0 | 完全没外层 Loop |
| **MCP / Function Calling** | 描述边界 + 协议层 | 工具能用 | 描述弱、无 MCP |

**我们当前在"Level 1 → Level 2 过渡期"**，基础约束建立中，**严重缺 Agent 能力本身（L2/L3/L4）**。

**Phase 1 必须先补 6 个能力**（Agent 能力本身，不是反馈回路）：
1. **AGENTS.md**（L1，把分散的 system prompt 收敛成项目级目录）
2. **Skills 真接入 chat 端点**（L2，把"老员工脑子里的规矩"用起来）
3. **Booking 改图结构**（L3，可控 Loop + 状态可视化 + 工具失败可恢复）
4. **Plan-and-Execute 模式**（L3，复杂任务先规划再执行）
5. **LTM 自动注入**（L4，记忆闭环：自动提取 + 自动注入 system prompt）
6. **工具权限分级 + Context 利用率监控**（L6，最小权限 + 防 40% 阈值）

**Phase 2 才做反馈回路**：
- 评测集 + RAGAS + 失败样本沉淀 + 自动回放
- HITL 接入 booking 高危操作
- Linter + 提示注入防御
- 暴露 /metrics

**Phase 3 才考虑平台化**：
- Multi-Agent 编排
- MCP 暴露工具
- Sub-agent 隔离
- 外层 Loop Engineering

**为什么不先做评测**：
- Agent 能力没做完（booking 还是硬编码 if-else、Skills 没用、LTM 没注入）→ 评测什么？
- 评测是"看 Agent 做得多好"——前提是"Agent 至少能稳定做完"
- 倒过来：能力做完 → 评测才有意义 → 反馈回路才能闭环

**核心金句**（来自 JavaGuide）：
> "大部分 Agent 项目跑起来不稳定，**不是模型不够好，是基础没搭好**。"
> "**Loop 真正的价值不在'Agent 会写代码'本身。模型、上下文和工具决定代码写得怎么样；Loop 负责把反馈、记录和停止条件放进流程里。**"
> "**如果你自己都说不清怎么验收，就别急着 loop。先把目标拆小，把验收标准写出来。**"
> "**先用最简单的方式跑通，再根据实际失败模式决定升级哪一层。** 上来就搞 Multi-Agent、全靠模型动态推理、上下文不做任何管理，踩进去了再爬出来会很费劲。"

---

## 附录 A：JavaGuide Agent 9 篇文档一览

| 文档 | 行数 | 核心 |
|------|------|------|
| [agent-basis.md](file:///E:/JavaGuide-main/docs/ai/agent/agent-basis.md) | 480 | Agent 演进 / ReAct / Plan-and-Execute / Workflow vs Agent |
| [harness-engineering.md](file:///E:/JavaGuide-main/docs/ai/agent/harness-engineering.md) | 550 | Model + Harness / 六层架构 / 40% 阈值 / OpenAI / Anthropic / Stripe / Hashimoto 实战 |
| [workflow-graph-loop.md](file:///E:/JavaGuide-main/docs/ai/agent/workflow-graph-loop.md) | 440 | Node / Edge / State / Loop 三要素 / Spring AI Alibaba / LangGraph |
| [context-engineering.md](file:///E:/JavaGuide-main/docs/ai/agent/context-engineering.md) | 435 | Context Rot / Lost in the Middle / Context Assembler / 三大武器 |
| [skills.md](file:///E:/JavaGuide-main/docs/ai/agent/skills.md) | 840 | SKILL.md 写法 / 渐进式披露 / 路由 / 8 大坑 |
| [loop-engineering.md](file:///E:/JavaGuide-main/docs/ai/agent/loop-engineering.md) | 600+ | 7 要素 / 4 类循环 / /loop / /goal / 什么场景值得做 |
| [mcp.md](file:///E:/JavaGuide-main/docs/ai/agent/mcp.md) | 425 | MCP 协议 / Tools / Resources / Prompts / JSON-RPC 2.0 |
| [prompt-engineering.md](file:///E:/JavaGuide-main/docs/ai/agent/prompt-engineering.md) | 650+ | 4 要素 / 6 技巧 / 调优流程 / 企业级安全 |
| [agent-memory.md](file:///E:/JavaGuide-main/docs/ai/agent/agent-memory.md) | 600+ | 短/长期 / 6 阶段 / Mem0 / Letta / 操作生命周期 |

## 附录 B：参考开源项目

- [Superpowers](https://github.com/obra/superpowers) — TDD / brainstorming / code review Skill
- [sanyuan-skills](https://github.com/sanyuan0704/sanyuan-skills) — Code Review Expert
- [Anthropic Skills](https://github.com/anthropics/skills) — 官方 skill-creator
- [skills.sh](https://skills.sh/) — 查找 Skill 的平台
- [goose (Block)](https://github.com/block/goose) — Stripe Minions 的底层

## 附录 C：关联文档

- [LONG_TERM_MEMORY_JAVAGUIDE_AI.md](LONG_TERM_MEMORY_JAVAGUIDE_AI.md) — JavaGuide AI 全 18 篇学习总览
- [PROJECT_AUDIT.md](PROJECT_AUDIT.md) — 旧版项目问题清单（v1）
- [PROJECT_OPTIMIZATION_PLAN.md](PROJECT_OPTIMIZATION_PLAN.md) — 优化路线（v1）
- [LONG_TERM_RAG_ROADMAP.md](LONG_TERM_RAG_ROADMAP.md) — RAG 长期路线
- [WEKNORA_LEARN.md](WEKNORA_LEARN.md) — 借鉴 WeKnora 的设计经验
