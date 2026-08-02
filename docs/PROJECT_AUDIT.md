# 项目问题清单 + 改进建议（基于 AgentScope 学习）

> 优先级：P0=必修，P1=应该做，P2=可做可不做

---

## P0 必修（影响业务可用性）

### 1. RAG rerank 没真正实现
- 位置：`app/rag/engine.py:258-260`
- 现状：`enable_rerank` 标记 True，但代码里没真实调用
- 影响：检索质量低，长文档召回准确度差
- 修复：接入真实 Rerank 模型（如 BGE-Reranker）
  ```python
  if enable_rerank:
      rerank_model = build_rerank_model()
      parent_hits = await rerank_model.rerank(query, parent_hits)
      rerank_applied = True
  ```

### 2. 向量库多租户 filter 格式可能不工作
- 位置：`app/rag/engine.py:217-223`
- 现状：Qdrant 和 Milvus 的 filter 语法不同，但代码用相同格式
- 影响：tenant_id 过滤可能失效，多租户数据可能串
- 修复：分离 Qdrant 和 Milvus 的 filter 构造

### 3. JWT secret 默认值在生产环境危险
- 位置：`app/core/config.py:175`（默认值警告已经在日志里）
- 现状：未设置 JWT_SECRET 环境变量时用默认值
- 影响：生产环境 token 可被伪造
- 修复：
  1. 启动时强制要求 JWT_SECRET
  2. 启动时拒绝使用默认值

---

## P1 应该做（影响系统能力）

### 4. 没有用 AgentScope 2.0 的 ReAct Agent
- 位置：`app/server/api.py` 的 chat 端点
- 现状：完全跳过了 AgentScope 的 `Agent` 类，自己写 LLM + 业务逻辑
- 影响：
  - 失去 ReAct 循环的工程优势
  - 工具调用逻辑散落在 `_handle_booking_flow` 里
  - 不容易扩展新工具
- 修复：让 LLM 通过工具调用自主决定走哪条流程
  ```python
  from agentscope.agent import Agent
  from agentscope.tool import Toolkit
  
  toolkit = Toolkit()
  toolkit.register(create_draft_order)
  toolkit.register(list_branches)
  # ...
  
  agent = Agent(name="美发顾问", system_prompt=..., model=model, toolkit=toolkit)
  return await agent.reply([user_msg])
  ```

### 5. Harness 工程缺失
- 现状：完全没有 HarnessAgent 的能力
- 影响：
  - Agent 不能从成功经验中学习（技能库）
  - 用户代码执行没有沙箱隔离
  - 没有 Plan 模式（先规划再执行）
- 建议：先实现 Skill Repository（最实用），再考虑 Sandbox 和 Plan

### 6. 状态持久化缺失
- 现状：服务器重启，正在进行的 Agent 任务会丢失
- 影响：用户长时间对话或服务器滚动发布时数据丢失
- 修复：
  1. 引入 AgentScope 的 AgentState 概念
  2. 实现 JsonFileAgentStateStore（开发用）
  3. 每次 call() 结束自动 saveToSession
  4. doCallInner 检测 pending 状态决定 coreAgent/resumeAgent

### 7. 中间件系统缺失
- 现状：没有 onAgent / onReasoning / onActing 拦截点
- 影响：
  - 日志、监控、限流没法统一加
  - 业务逻辑和横切关注点耦合
- 建议：先实现 1-2 个最实用的中间件（统计、日志）

### 8. HITL（人在回路）缺失
- 现状：没有让 Agent 在危险操作前停下来等用户审批
- 影响：商户取消订单、改时间等操作没有人工确认
- 建议：
  1. 实现权限三态引擎（ALLOWED/ASKING/DENIED）
  2. 危险操作触发 RequireUserConfirmEvent
  3. 前端展示确认弹窗

### 9. 事件流系统缺失
- 现状：前端看不到"模型正在打字""正在调用工具"
- 影响：用户体验差
- 修复：
  1. 用 SSE（Server-Sent Events）实现流式响应
  2. 后端推送 28 种 AgentEvent
  3. 前端订阅 EventSource，实时更新 UI

### 10. 完整测试覆盖
- 现状：完全没有测试
- 影响：任何修改都可能破坏现有功能
- 建议（优先级从高到低）：
  1. 单元测试：每个工具函数、模型工厂
  2. 集成测试：API 端点
  3. E2E 测试：核心业务流程
  4. 性能测试：高并发

---

## P2 可做可不做（锦上添花）

### 11. 长期记忆没跨会话
- 现状：chat_messages 是按用户存，但没提取"用户偏好"等长期记忆
- 修复：增加一层"事实提取"中间件，识别并保存"用户说过的偏好"

### 12. 多智能体协作
- 现状：一个 Agent 干所有事（booking + knowledge + casual）
- 修复：拆成 3 个子 Agent（BookingAgent / KnowledgeAgent / CasualAgent），由主 Agent 编排

### 13. 文档解析不够鲁棒
- 现状：基本只支持 TextBlock
- 修复：增加 PDF、Word、Excel 的解析（其实代码里有，但没启用）

### 14. 没 Rate Limiting
- 现状：用户可以无限制刷接口
- 修复：加 slowapi 限流

### 15. 监控告警
- 现状：prometheus-client 装了但没用
- 修复：
  1. 暴露 /metrics 端点
  2. 关键指标：对话 QPS、平均响应时间、Token 消耗、错误率
  3. 接入 Grafana

### 16. 没 CSRF 保护
- 现状：JWT 在 header 里，理论上 CSRF 风险低，但有 Origin 检查
- 修复：CORS 严格白名单

### 17. 错误处理不健壮
- 现状：工具失败没有 retry 机制
- 修复：
  1. 工具装饰器：自动 retry 3 次
  2. 软失败：tool 返回错误结果时，Agent 还能继续
  3. 超时控制：每个工具 30s 超时

### 18. i18n 缺失
- 现状：所有提示都是中文
- 修复：抽离到资源文件

---

## 关键 bug 修复（已修）

- LLM 意图识别替代关键词匹配
- chat 端点分离 booking / knowledge / casual
- 自动创建草稿订单 + 引导选分店
- chat_messages 长期记忆
- 三重冲突检查（门店/发型师/时间段）
- 选项卡片 + 点击交互

---

## 改进路线图（建议）

### Phase 1：稳定性（P0）
1. 接入真实 Rerank 模型
2. 修复向量库 filter 格式
3. JWT secret 强制检查

### Phase 2：企业级能力（P1）
1. 切换到 AgentScope ReAct Agent
2. 实现 AgentState 状态持久化
3. 实现中间件系统
4. HITL 权限三态
5. SSE 事件流

### Phase 3：高级功能（P2）
1. HarnessAgent 技能库
2. 多智能体编排
3. 长期记忆提取
4. 监控告警
