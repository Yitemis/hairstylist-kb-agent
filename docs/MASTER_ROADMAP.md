# 🎯 综合路线图（Master Roadmap）

> 综合 8 份学习文档 + 当前进度，给出 **3 周冲刺计划**
> 优先级 = 业务可用性 × 面试加分 × 实现成本

---

## 📚 综合的 8 份学习文档

| 文档 | 来源 | 关注点 |
|------|------|--------|
| INTERVIEW_NOTES | MVP-1~6 + L1-P1-01/02/04 等 | 已完成项的面试话术 |
| PROJECT_AUDIT | 12 项待办（P0/P1/P2） | 风险 + 补全 |
| PROJECT_OPTIMIZATION_PLAN | L0-L8 模块路线 | 详细任务拆分 |
| LONG_TERM_MEMORY_EKBS | 九阳企业知识库 | 父子分块 + LLM 抽象 |
| LONG_TERM_MEMORY_JOYOUNG_POC | 九阳 POC 实战 | 12 类场景应对 |
| LONG_TERM_MEMORY_JAVAGUIDE_AI | LLM/RAG/Agent 体系 | 概念 + 策略表 |
| LONG_TERM_MEMORY_AI_AGENT | AI Agent 知识 | ReAct / Tool use |
| **JAVAGUIDE_LEARNING** | JavaGuide 8 篇必读 | **高可用 / 高性能 / 分布式** |

---

## ✅ 已完成（15 次 commit）

| Stage | 任务 | 状态 |
|-------|------|------|
| **Stage 1** | Milvus / PG / MinerU / Alembic / 父子分块 | ✅ 6/6 |
| **Stage 2** | BM25 / 6 策略 / HITL / 记忆 / SSE / Prometheus / VLM | ✅ 7/7 |
| **跨阶段** | RBAC audience / 多模态 chat / LLM 缓存幂等 / ModelRouter 5 capability | ✅ 4/4 |

**测试 149 passed，43 个 file，~5000 行核心代码**

---

## ❌ 综合所有文档得出的"未做"清单

### P0（必做 - 影响生产可用性）

| # | 任务 | 来源 | 风险 | 时间 |
|---|------|------|------|------|
| 1 | **熔断 + 降级** | JAVAGUIDE_LEARNING + AUDIT | 火山方舟欠费时**整个 chat 500** | 1 天 |
| 2 | **订单幂等** | JAVAGUIDE_LEARNING + AUDIT | 重复点击 → 多个订单 / 重复扣款 | 0.5 天 |
| 3 | **JWT secret 默认值** | AUDIT P0 | 生产环境**用 dev key = 严重安全风险** | 0.5 天 |
| 4 | **多租户 filter 格式** | AUDIT P0 | Milvus filter 可能**完全不工作** | 0.5 天 |
| 5 | **数据热冷分离** | JAVAGUIDE_LEARNING | 聊天/订单无限膨胀，**PG 性能崩** | 1 天 |

### P1（重要 - 影响能力）

| # | 任务 | 来源 | 价值 | 时间 |
|---|------|------|------|------|
| 6 | **Rerank 真正接入** | AUDIT | 我们已用硅基流动 ✅ | 0.5 天 |
| 7 | **ReAct Agent 升级** | AUDIT + AI_AGENT | 智能体能力 | 1.5 天 |
| 8 | **Context compression** | OPTIMIZATION_PLAN L1-P1-03 | 长上下文减成本 | 1 天 |
| 9 | **Knowledge 增量更新** | OPTIMIZATION_PLAN L1-P1-04 | 文档更新不重建 | 1 天 |
| 10 | **Evaluation set** | OPTIMIZATION_PLAN L1-P1-05 | 量化 RAG 效果 | 1 天 |
| 11 | **RAG 3 层校验** | OPTIMIZATION_PLAN L1-P1-02 | 质量保证 | 1 天 |
| 12 | **CI/CD（GitHub Actions）** | 简历 | 自动测试 + 部署 | 1 天 |

### P2（完善 - 锦上添花）

| # | 任务 | 来源 | 时间 |
|---|------|------|------|
| 13 | **分布式锁** | JAVAGUIDE_LEARNING | 0.5 天 |
| 14 | **分布式事务 outbox** | JAVAGUIDE_LEARNING | 1 天 |
| 15 | **雪花 ID** | JAVAGUIDE_LEARNING | 0.5 天 |
| 16 | **数据脱敏** | JavaGuide 安全 | 0.5 天 |
| 17 | **多智能体协作** | LONG_TERM_MEMORY_AI_AGENT | 2 天 |
| 18 | **K8s Helm Chart** | ENTERPRISE_PLAN | 2 天 |
| 19 | **前端完善** | PRD | 2-3 天 |

---

## 🎯 综合路线图（**3 周冲刺**）

### **Week 1：高可用 + 安全**（**最重要**）

| 日 | 任务 | 产出 | 来源 |
|---|------|------|------|
| **1** | **P0-3 JWT secret 强制校验** | lifespan 启动校验 | AUDIT |
| **1** | **P0-4 Milvus filter 测试** | 补测试，确认工作 | AUDIT |
| **2** | **P0-1 熔断 + 降级**（pybreaker） | circuit_breaker.py + 测试 | JAVAGUIDE |
| **3** | **P0-2 订单 + 支付幂等** | Idempotency-Key 中间件 | JAVAGUIDE |
| **4-5** | **P0-5 数据热冷分离** | 归档定时任务（APScheduler） | JAVAGUIDE |
| **5** | **P2-16 数据脱敏**（手机号） | desensitize 工具 | JavaGuide |

**Week 1 产出**：
- 火山方舟欠费 → **自动降级**（RAG 走纯文本）
- 用户点 100 次支付 → **只扣 1 次**
- 1 年前的聊天 → **自动归档**
- 生产环境 → **强制 JWT secret**
- 简历可写：*"高可用 + 安全设计经验"*

### **Week 2：性能 + 监控 + CI/CD**

| 日 | 任务 | 产出 | 来源 |
|---|------|------|------|
| **6-7** | **P1-8 Context compression** | LLMLingua / 长文压缩 | OPTIMIZATION_PLAN |
| **7** | **P1-11 RAG 3 层校验** | 文档级 / 块级 / 答案级 | OPTIMIZATION_PLAN |
| **8** | **P1-10 Evaluation set** | 50 个测试 query + recall@k | OPTIMIZATION_PLAN |
| **9-10** | **P1-12 CI/CD** | GitHub Actions（test + build + deploy）| 简历 |

**Week 2 产出**：
- 长上下文成本 -30%
- RAG 质量可量化
- 简历可写：*"完整 DevOps 经验"*

### **Week 3：分布式 + 高级**

| 日 | 任务 | 产出 | 来源 |
|---|------|------|------|
| **11-12** | **P2-13 分布式锁** | pg_advisory_xact_lock | JAVAGUIDE |
| **13** | **P2-14 分布式事务 outbox** | outbox 表 + worker | JAVAGUIDE |
| **14** | **P2-15 雪花 ID** | Snowflake 实现 | JAVAGUIDE |
| **15** | **P1-9 Knowledge 增量** | hash 感知，差量更新 | OPTIMIZATION_PLAN |

**Week 3 产出**：
- 订单 100% 不超卖
- 分布式消息不丢
- 简历可写：*"分布式系统实战"*

---

## 🎯 立即可做的 Top 3（**今天**）

按"简历加分 × 业务影响"：

### 1. **熔断 + 降级**（JAVAGUIDE 推荐）⭐⭐⭐
- **影响**：解决"火山方舟欠费时整个 chat 500"
- **时间**：1 天
- **产出**：`circuit_breaker.py` + 中间件 + 测试
- **面试话术**：*"借鉴 Resilience4j 设计，实现 LLM 调用熔断 + 降级"*

### 2. **JWT secret 强制校验**（AUDIT 推荐）⭐⭐
- **影响**：生产安全**严重风险**（默认 dev key）
- **时间**：0.5 天
- **产出**：lifespan 启动 fail-fast + 强密码生成器
- **面试话术**：*"生产环境强校验，避免配置错误"*

### 3. **Milvus filter 实际测试**（AUDIT 推荐）⭐⭐
- **影响**：多租户隔离**可能完全不工作**（最大风险）
- **时间**：0.5 天
- **产出**：端到端测试（验证 audience / category / tenant 都能 filter）

---

## 📊 决策矩阵

| 决策维度 | 评分 |
|---------|------|
| **业务可用性** | 熔断 10 / 订单幂等 9 / JWT 9 / 归档 7 |
| **面试加分** | 熔断 9 / CI/CD 9 / 订单幂等 8 / 雪花 6 |
| **实现难度** | JWT 简单 / Milvus 简单 / 熔断 中 / 订单幂等 中 / 归档 难 |

**我的推荐（按 ROI 排序）**：

1. **JWT 强制校验**（30 分钟，先做）→ 0.5 天
2. **Milvus filter 测试**（1 小时）→ 0.5 天
3. **熔断 + 降级**（核心）→ 1 天
4. **订单幂等**（业务价值大）→ 0.5 天
5. **数据归档**（性能 + 实战）→ 1 天
6. ...

---

## 🎤 综合路线图的"面试故事线"

> "我们项目经历 3 个阶段：
> - **MVP（Week 1）**：RAG 三件套（Milvus + PG + BM25） + 父子分块
> - **生产化（Week 2）**：多模态 + RBAC + SSE + 监控 + 幂等
> - **高可用（Week 3）**：**熔断降级 + 订单幂等 + 数据归档 + JWT 强校验**
> 
> 借鉴的是 **JavaGuide 高可用设计**（idempotency + fallback + circuit-breaker），用 **pybreaker 实现 LLM 熔断**，用 **Idempotency-Key 实现订单幂等**，用 **APScheduler 实现数据归档定时任务**。"

---

## ✅ 接受这个路线图吗？

**接下来 3 周**（15 个工作日）：
- **Week 1**：高可用 + 安全（**5 个 P0**）
- **Week 2**：性能 + 监控 + CI/CD（**5 个 P1**）
- **Week 3**：分布式 + 高级（**5 个 P2**）

**总产出**：
- 18 个新功能
- 60+ 个新测试
- 简历可写 5 段项目经验
- 面试可讲 20+ 个设计决策

要按这个路线图开干吗？还是想调整顺序 / 范围？
