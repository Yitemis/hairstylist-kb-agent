# JavaGuide 学习笔记 - 搭建系统必备知识

> 学习源：`E:\JavaGuide-main`（124K stars，Java 开发者面试圣经）
> 提炼对我们**美发知识助手**项目最相关的章节
> 对比现状 → 补全路线

---

## 📚 核心 4 大主题（跟我们项目强相关）

| 主题 | 章节 | 我们做了 | 还需补 |
|------|------|----------|--------|
| **高可用** | idempotency / fallback / retry / limit | 50% | 50% |
| **高性能** | hot-cold / pagination / sql / read-write | 30% | 70% |
| **分布式** | id / lock / transaction | 20% | 80% |
| **安全** | jwt / 脱敏 / 敏感词 | 70% | 30% |

---

## 🎯 我们项目最重要的 8 篇文章

### 【高可用】

#### 1. **idempotency.md**（高可用目录）
> **JavaGuide 核心思想**：
> - 幂等 4 要素：唯一 key + 状态机 + 持久化 + 过期
> - 客户端传 `Idempotency-Key: <uuid>`
> - 服务端：第一次调实际执行，后续直接返回缓存结果
> - 4 种场景：表单重复提交 / 接口重复调用 / 消息重复消费 / 支付重复回调

> **我们状态**：
> - ✅ LLM 响应缓存（1h TTL，sha256 消息 hash）
> - ✅ 提问幂等（24h TTL，user_id + message 兜底 hash）
> - ❌ **订单幂等**（用户点多次创建订单 → 同一订单）⚠️ 重要
> - ❌ **支付幂等**（用户重复付款 → 重复扣款）⚠️ 关键

> **待补**：
> - 订单创建加 `Idempotency-Key` 头（防重复下单）
> - 支付回调加 `trade_no` 唯一索引（防重复扣款）

#### 2. **fallback-and-circuit-breaker.md**（高可用目录）
> **JavaGuide 核心思想**：
> - **降级**：服务挂了返回默认值（缓存 / 默认回复）
> - **熔断**：连续失败 N 次熔断 M 秒（防止雪崩）
> - 状态机：CLOSED → OPEN → HALF_OPEN
> - 3 种实现：Hystrix / Resilience4j / Sentinel

> **我们状态**：
> - ❌ **完全没做**（LLM 欠费时整个 chat 端点 500）
> - ❌ 没监控熔断（embedding 连续失败会拖垮所有 RAG）

> **待补**（**P0 优先级**）：
> - 火山方舟 multimodal 欠费 → RAG 应降级到纯文本路径
> - LLM 连续 3 次失败 → 熔断 30s，返回"系统繁忙"
> - 用 `pybreaker` 库（最简单）

#### 3. **timeout-and-retry.md**（高可用目录）
> **JavaGuide 核心思想**：
> - 3 个超时：连接超时 / 读超时 / 整体超时
> - 3 种重试：立即重试 / 退避重试 / 指数退避
> - 重试雪崩：重试 + 雪崩 = 雪崩²
> - 方案：限流 + 熔断 + 隔离

> **我们状态**：
> - ✅ LLM 5 次重试（`max_retries=5`，`retry_delay=2s`）
> - ✅ embedding 也有重试
> - ❌ **没有超时配置**（AgentScope 默认可能 30s+）
> - ❌ **没有指数退避**（固定 2s）

> **待补**：
> - httpx 客户端统一超时（connect=5s / read=30s / write=30s）
> - 指数退避：2s → 4s → 8s → 16s → 32s

### 【高性能】

#### 4. **data-cold-hot-separation.md**（高性能目录）
> **JavaGuide 核心思想**：
> - **热数据**：最近 3 个月的，访问频繁
> - **冷数据**：3 个月以上的，归档
> - 物理隔离：热数据 SSD，冷数据 HDD / S3
> - 归档策略：定时任务（每天凌晨）

> **我们状态**：
> - ❌ **没做**（所有数据都存 PG，未来会膨胀）
> - ❌ 订单历史、聊天历史会越来越大
> - ❌ Milvus collection 没清理

> **待补**：
> - 6 个月前的 `chat_messages` 归档到 S3 / OSS
> - 6 个月前的订单移到 `orders_archive` 表
> - Milvus 冷数据 vector 删掉（保留 PG parent_chunks 即可）

#### 5. **deep-pagination-optimization.md**（高性能目录）
> **JavaGuide 核心思想**：
> - 5 种方案：子查询 / 延迟关联 / 游标分页 / 覆盖索引 / ES
> - **游标分页**（keyset pagination）：`WHERE id > last_id LIMIT 20`（不变）
> - 禁用 `LIMIT 100000, 20`（O(n) 慢）

> **我们状态**：
> - ❌ **没注意**（订单列表 / 聊天历史可能深分页慢）

> **待补**：
> - 订单列表改用 `WHERE order_id > last_id`
> - 聊天历史用 `message_id` 游标

### 【分布式】

#### 6. **distributed-lock.md**（分布式目录）
> **JavaGuide 核心思想**：
> - 3 种实现：DB 唯一索引 / Redis SETNX / Zookeeper
> - 简单方案：PG `SELECT ... FOR UPDATE` 或 `INSERT ... ON CONFLICT`
> - 锁粒度：宁可粒度小（按订单 ID）也别粒度大（全局锁）

> **我们状态**：
> - ❌ **没做**（并发下订单可能超卖）
> - ❌ 多个员工同时改同一订单可能冲突

> **待补**：
> - 订单状态机加悲观锁：`SELECT ... FOR UPDATE`
> - 或用 advisory lock：`SELECT pg_advisory_xact_lock(order_id)`

#### 7. **distributed-transaction.md**（分布式目录）
> **JavaGuide 核心思想**：
> - 3 种方案：2PC / TCC / Saga
> - 简单方案：**本地消息表**（最常用）
> - 失败重试 + 幂等 + 补偿

> **我们状态**：
> - ❌ **没做**（订单 + 库存 + 支付是分布式）
> - ❌ 订单创建后如果通知失败 → 数据不一致

> **待补**（中优先级）：
> - `outbox` 表存待发送消息
> - 后台 worker 轮询发送（at-least-once + 幂等）

#### 8. **distributed-id.md**（分布式目录）
> **JavaGuide 核心思想**：
> - UUID：随机，无序，DB 索引分裂（不推荐）
> - **雪花算法**（Snowflake）：1 bit + 41 bit 时间 + 10 bit 机器 + 12 bit 序列
> - 美团 Leaf / 百度 UidGenerator（生产级）
> - 数据库自增：简单但单点

> **我们状态**：
> - ✅ UUID（`str(uuid.uuid4())`）够用
> - ❌ **雪花算法未用**（高并发下 UUID 也行，雪花更好）

> **待补**（低优先级）：
> - 雪花算法生成 `parent_id` / `image_id`（有序 + 性能更好）

---

## 🔐 安全模块（4 篇 + 我们对照）

| 文章 | 我们状态 | 备注 |
|------|----------|------|
| jwt-intro.md | ✅ | 已用 |
| design-of-authority-system.md | ✅ | RBAC audience 隔离 |
| data-desensitization.md | ⚠️ 部分 | 手机号应脱敏 `138****0000` |
| sentive-words-filter.md | ✅ | safety_filter |
| encryption-algorithms.md | ⚠️ | 密码用 `hash_password`（bcrypt）✅ |
| data-validation.md | ⚠️ | Pydantic 部分用 |

---

## 🎤 JavaGuide 教我们怎么面试

### 经典系统设计题（高频）

| 题目 | 我们怎么答 |
|------|-----------|
| **短链系统** | 类比：知识库 doc_id → 短链 |
| **秒杀系统** | 类比：用户抢着预约发型师 → Redis 限流 + 分布式锁 |
| **微博 feed 流** | 类比：商家 / 用户各自看到不同 KB → 关注流 + RBAC |
| **评论系统** | 类比：多轮对话 + 长期记忆 |
| **分布式锁** | 我们 `pg_advisory_xact_lock` 即可 |
| **消息队列** | 我们 `outbox` 表即可 |
| **搜索系统** | 我们 RAG = 向量 + BM25 + RRF（**3 路融合**比单 ES 强）|
| **限流** | 我们中间件 + Redis 漏桶 |
| **分布式 ID** | 我们 UUID → 升级雪花 |
| **高可用** | 我们多副本 + 限流 + 熔断（待补）|

### 项目自述（用 JavaGuide 话术）

> "我们项目借鉴 **JavaGuide 高可用 + 高性能 + 分布式** 三大设计原则：
> - **高可用**：幂等（提问 + 订单）+ 限流（API 中间件）+ 熔断（**待补**）
> - **高性能**：BM25 + 向量 + RRF 三路融合（**借鉴 JavaGuide 的搜索系统**）
> - **分布式**：PG + Milvus + Redis 三件套（**借鉴 JavaGuide 分布式 ID 章节**）
> - **安全**：JWT + audience RBAC 隔离（**借鉴权限系统设计章节**）"

---

## ✅ 接下来 7 天的补全路线（基于 JavaGuide 优先级）

### **P0（必做 - 1 周内）**
1. **降级与熔断**（fallback-and-circuit-breaker） - 1 天
   - LLM 欠费时 RAG 降级到纯文本路径
   - 连续失败熔断（pybreaker）
   - 加 `circuit_breaker` 模块 + 测试

2. **超时与重试**（timeout-and-retry） - 0.5 天
   - httpx 统一超时（5/30/30）
   - 指数退避（2/4/8/16/32s）

3. **数据热冷分离**（data-cold-hot-separation） - 1 天
   - 6 个月聊天历史归档
   - 订单归档表

### **P1（重要 - 2 周内）**
4. **深分页优化**（deep-pagination-optimization） - 0.5 天
5. **分布式锁**（distributed-lock） - 0.5 天
6. **订单幂等**（idempotency） - 0.5 天
7. **数据脱敏**（data-desensitization） - 0.5 天

### **P2（完善 - 1 个月内）**
8. 分布式事务（outbox） - 1 天
9. 分布式 ID（雪花） - 0.5 天
10. SQL 优化（EXPLAIN） - 0.5 天

---

## 📖 重点要读的 5 篇（按优先级）

1. **idempotency.md** ⭐⭐⭐ - 跟我们的 LLM 缓存/幂等直接对应
2. **fallback-and-circuit-breaker.md** ⭐⭐⭐ - 补我们缺的熔断
3. **distributed-transaction.md** ⭐⭐ - 补我们缺的事务
4. **design-of-authority-system.md** ⭐⭐ - 复习我们的 RBAC
5. **data-cold-hot-separation.md** ⭐ - 性能必修

---

## 🎯 给我自己的启示

**看完 JavaGuide 后我意识到**：

1. **我们缺 3 个 P0**：熔断、超时配置、热冷分离
2. **幂等做了一半**：LLM 做了，订单没做
3. **分布式能力弱**：PG 唯一索引替代分布式锁可以，但 outbox 事务没做
4. **可观测性有但弱**：Prometheus + Loki 日志没接入
5. **CI/CD 缺**：没 GitHub Actions

**接下来 3 个最有价值的**：
1. **熔断**（防止火山方舟欠费时整个 chat 崩） - **今天**
2. **数据归档**（PG 不会无限膨胀） - 明天
3. **CI/CD**（简历亮点） - 后天
