# AI Agent 长期学习记忆

> 这是我从学习资料中总结的核心知识，作为我后续开发和打磨项目的长期记忆。
> 每学到一个新概念会持续更新。

---

## 1. 核心架构（AgentScope 范式）

### 1.1 一个生产级 Agent 框架的"五层架构"

```
┌─────────────────────────────────────────────┐
│ 第5层 Harness工程                             │
│  - 技能库（Skill Repository）                  │
│  - 沙箱（Sandbox）                              │
│  - Plan 模式（先规划再执行）                    │
│  - Workspace（多租户文件隔离）                 │
│  - Subagent 编排                                │
├─────────────────────────────────────────────┤
│ 第4层 状态持久化                                │
│  - AgentState 统一状态快照                     │
│  - AgentStateStore 接口 + 多后端（文件/Redis/MySQL）│
│  - 每次 call() 自动保存                         │
│  - safe(filename) 防路径遍历                    │
├─────────────────────────────────────────────┤
│ 第3层 控制治理                                  │
│  - 5种中间件（onAgent/onReasoning/onActing/    │
│    onModelCall/onSystemPrompt）                │
│  - 权限三态引擎（ALLOWED/ASKING/DENIED）        │
│  - HITL 人在回路（RequestStop + 恢复）         │
├─────────────────────────────────────────────┤
│ 第2层 核心引擎                                  │
│  - ReAct 循环（reasoning ↔ acting）             │
│  - ModelRegistry + SPI 插件化                  │
│  - Toolkit 工具系统 + MCP                       │
├─────────────────────────────────────────────┤
│ 第1层 数据地基                                  │
│  - 统一消息模型（Msg = 角色 + ContentBlock[]）  │
│  - 事件流（28种 AgentEvent）                    │
│  - ContentBlock sealed class 体系              │
└─────────────────────────────────────────────┘
```

### 1.2 ReAct 循环的本质

```
用户输入
  ↓
[Reasoning] LLM 思考：要不要调工具？调哪个？
  ↓
判断 isFinished() = output 没有 ToolUseBlock？
  ├─ 是 → 返回最终 Msg
  └─ 否 → [Acting] 执行工具
              ↓
         权限三态判定
              ↓
         收集 ToolResultBlock 塞回 context
              ↓
         回到 [Reasoning] 下一轮 iter
```

关键洞察：
- isFinished() 判定极简：output 没有 ToolUseBlock 就退出
- 每次推理需要 maxIters 兜底，防止无限循环
- Pending 状态检测决定"从头开始"还是"从挂起处恢复"

---

## 2. 关键设计模式（可复用）

### 2.1 消息模型
- 不可变 + withXxx 复制式修改 → 并发安全
- 防御性拷贝 → 外部集合先拷贝再存，防篡改
- Fail-Fast 构造期校验 → 非法状态无法被表示
- metadata 扩展槽 + 常量 key → 不改核心结构就能扩展
- SYNTHETIC 标记 → 区分真实历史 vs 临时提示

### 2.2 中间件洋葱模型
4 种洋葱模式 + 1 种管道模式：
- onAgent: 最外层，整个 Agent 执行
- onReasoning: 推理阶段（调模型）
- onActing: 行动阶段（调工具）
- onModelCall: 最内层，模型 API 调用
- onSystemPrompt: 管道，变换 system prompt

洋葱链 = middleware[A, B, C] 嵌套调用 core

### 2.3 状态持久化
- AgentState = 一切状态快照
- AgentStateStore 接口 = (userId, sessionId, key) → State
- 多后端：JsonFile / InMemory / Redis / MySQL / PostgreSQL / OSS / COS
- safe(filename) = 正则 + Base64 防路径遍历
- interruptControl 标记 transient（不持久化）
- 每次 call() 结束自动 saveToSession

### 2.4 HITL 人在回路
权限判定 → ALLOWED/ASKING/DENIED
→ ASKING 工具存在 → 推 RequireUserConfirmEvent + RequestStopEvent
→ Agent 循环安全退出，挂起
→ 用户批准 → 再次 call() → doCallInner 检测 pending
→ 走 resumeAgent() 从 acting 阶段直接恢复

### 2.5 记忆分层
| 层级 | 对应 | 持久化方式 |
|------|------|------------|
| 工作记忆 | 本轮对话 context | 内存 + 每次 call() 自动保存 |
| 长期记忆 | 跨会话用户偏好 | 应用层自行实现（业务数据库） |
| 笔记 | MEMORY.md（Agent 自我笔记） | 文件系统，HarnessAgent 自动管理 |

---

## 3. RAG 引擎最佳实践

### 3.1 标准流水线
```
bytes → Parser → Section[] → Chunker → Chunk[]
                                      ↓
                                KnowledgeBase.insert_document
                                      ↓
                                embed → store on collection

search: knowledge.search(query) → VectorSearchResult
```

### 3.2 父子分块检索
```
查询 → embed → 向量库召回 Top-FetchK 子块
            ↓
       按 parent_id 聚合去重 → Rerank 精排
            ↓
       返回 Top-K 父块（完整上下文）
```

### 3.3 Self-RAG（自主反思）
无结果 → 加领域关键词重试
最高分 < 阈值 → 加领域限定词重试
命中数 < 2 → 扩大召回范围重试
最多 max_retries 次

### 3.4 RAGMiddleware 自动注入
在 onReasoning 阶段自动把检索结果注入到 system prompt
核心代码零改动，所有 Agent 自动具备 RAG 能力

---

## 4. 关键反模式（避免）

### 反模式 1：用关键词做意图识别
- BAD：keywords = ["烫", "染", "剪"]; if any... return "booking"
- GOOD：用 LLM 做意图分类

### 反模式 2：绕过 Agent 自己写对话逻辑
- BAD：if "预约" in input: return booking_logic()
- GOOD：让 LLM 通过工具调用自主决定

### 反模式 3：可变消息对象
- BAD：msg.content.append(new_block)
- GOOD：msg = msg.withContent([...new_blocks])

### 反模式 4：硬编码状态生命周期
- BAD：self.pending_tool_calls = [...]  # 服务器重启就丢
- GOOD：持久化到 AgentState

---

## 5. 知识来源
- C:\Users\18414\Desktop\学习\*.md（11 篇教程）
- E:\agentscope-java-main\（生产级 Java 源码）
- E:\agentscope-main\（Python 源码，我们用的版本）

重点章节：
- 00-总览与学习地图.md
- 01-消息模型.md
- 03-ReAct核心引擎.md
- 06-中间件权限与HITL.md
- 07-记忆与状态持久化.md
- 08-Harness工程.md

---

## 6. 与本项目相关的关键决策记录

| 决策 | 原因 |
|------|------|
| 用 LLM 替代关键词做意图识别 | 关键词脆弱，LLM 灵活 |
| chat_messages 表做长期记忆 | 简单可靠，可扩展 |
| chat 端点分离 booking / knowledge / casual 路径 | 不同意图不同处理 |
| 订单 draft → pending 状态机 | 支持分步填写 |
| 三重冲突检查（门店容量/发型师容量/时间段） | 业务必需 |
| 前端可点击选项卡片 | 对话 + 点击 双通道 |
| 草稿订单"继续编辑"按钮 | 防止用户重复输入 |
