# 【临时文档·后续删除】产品升级方案：双角色 + 对话式下单

> ⚠️ 本文档为开发阶段的临时记录，功能落地后即可删除。
> 创建日期：2026-07-30
> 状态：设计阶段（Figma 出稿中）

---

## 0. 为什么写这份文档

记录 2026-07-30 与 Claude 讨论的产品方向升级，避免跨对话遗忘。
核心变化：从「纯知识库问答」升级为「双角色 + 对话式智能下单系统」。

---

## 1. 产品定位升级

### 原定位
纯美发行业知识库问答助手（B 端，给发型师/店员查专业知识）。

### 新定位
双角色美发店智能系统：
- **店家端（B 端）**：知识库问答 + 订单管理后台 + 知识库管理 + 数据统计
- **用户端（C 端）**：通过与 Agent 对话，一步步完善并生成美发预约订单

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    美发智能助手系统                      │
├──────────────────────────────────┬──────────────────────┤
│       👤 用户端（C 端）           │   🏪 店家端（B 端）   │
│                                  │                      │
│  • 对话式预约下单                 │  • 知识库问答         │
│  • AI 引导选项目/发型师/时间      │  • 订单管理后台       │
│  • 智能推荐（根据用户情况）        │  • 知识库管理         │
│  • 订单确认/修改/取消             │  • 数据统计           │
└──────────────────────────────────┴──────────────────────┘
```

登录时按账号角色区分，进入不同界面。

---

## 3. 核心功能：对话式下单（用户端）

### 3.1 交互理念
用户不需要填表单，而是像和前台聊天一样，Agent 通过判断用户意图，
一步步引导用户完善订单，最终以订单形式返回。

### 3.2 订单需要收集的字段
1. **时间**（预约日期 + 时间段）
2. **店铺地址**
3. **联系电话**
4. **要做的项目**（烫发/染发/护理/剪发...）
5. **选的发型师**

### 3.3 智能引导场景（关键卖点）
- 用户不知道做什么项目 → Agent 询问需求（发质、场合、预算），推荐项目
- 用户不知道想要什么发型 → Agent 结合用户情况推荐发型
- Agent 通过判断用户意图，逐步满足用户心理预期
- 所有信息确认后，以订单卡片形式汇总返回

### 3.4 订单状态流转
pending（待确认）→ confirmed（已确认）→ completed（已完成）
                                        ↘ cancelled（已取消）

---

## 4. 界面设计（Figma）

### 已完成
- ✅ 店家端知识库问答界面（三栏：会话列表 + 聊天区 + 知识库面板），效果满意

### 待生成
- ⬜ 用户端：对话式预约下单界面（左侧实时订单摘要 + 右侧聊天区）
- ⬜ 店家端：订单管理页面 + 知识库管理页面

### 用户端界面提示词要点
- 三/两栏布局，左侧实时订单摘要面板（已确认=绿色勾选，待确认=灰色问号）
- 对话式引导：信息收集卡片（单选/多选）、发型师选择卡片、时间选择器、订单确认卡片
- 配色：暖紫 #8B5CF6 + 香槟金 #F59E0B
- 风格：温暖、贴心，像前台接待

### 店家端订单管理提示词要点
- 左侧深色导航：智能问答 / 订单管理 / 知识库管理 / 数据统计
- 订单列表卡片：用户信息 + 项目 + 时间 + 发型师 + 状态标签 + 操作按钮
- 点击展开：完整对话历史、用户需求、AI 推荐记录
- 状态色：绿(已确认)/橙(待确认)/红(已取消)

---

## 5. 数据表初步设计（待细化）

> 存储方案后续再定，先记录字段规划。

### users（用户）
```
id, phone, name, avatar, created_at
```

### staffs（店家/员工）
```
id, phone, name, avatar, role, password_hash, created_at
```

### stylists（发型师）
```
id, name, avatar, specialties, description, is_active
```

### orders（订单，核心）
```
id, user_id, stylist_id,
service_type, service_details,
appointment_date, appointment_time,
phone, address, note,
status: pending | confirmed | completed | cancelled,
conversation_history: JSON,   // 完整对话记录
created_at, updated_at
```

### services（服务项目）
```
id, name, category, duration_minutes, price, description
```

---

## 6. 技术栈决策

- 前端：Figma AI 生成设计（自然语言提示词） → Claude 还原为代码
- 后端：已有 FastAPI + AgentScope + RAG 引擎（Milvus）
- 前后端配合流程：Claude 出 Figma 提示词 → 用户在 Figma 生成 → 评审 → Claude 迭代提示词

---

## 7. 待办 / 下一步

- [ ] Figma 生成用户端对话下单界面
- [ ] Figma 生成店家端订单管理 + 知识库管理界面
- [ ] 设计定稿后写前端代码
- [ ] Agent 新增「订单管理工具」（对话式收集订单字段 + 意图判断 + 推荐）
- [x] ~~设计数据表 + 选定存储方案~~ → 落到 docs/TEMP_数据库设计.md + SQLite
- [x] ~~登录 / 角色区分逻辑~~ → 已完成 4 个 auth 接口（手机号+密码）
- [x] ~~修复 app/server/api.py 缩进问题~~ → 已修
- [x] ~~升级 agentscope 到 2.0~~ → 已完成，重写 agent_factory / model_factory / tool_registry + 修 /chat 端点

---

## 8. 已知待修复问题

- ~~app/server/api.py 缩进错乱~~ ✅ 已修
- ~~agentscope 0.x → 2.0 升级~~ ✅ 已完成：
  - `Agent`（不再是 `ReActAgent`），无 `memory` 参数，对话上下文由 AgentState 管理
  - `await agent.reply(UserMsg(...))` 返回 `Msg`；`Msg.content` 是 `ContentBlock` 列表（不再直接是字符串）
  - 工具：`FunctionTool` + `Toolkit`（不再是 `from agentscope.tools import tool`）
  - 模型：`OpenAIChatModel` + `OpenAICredential`（不再是 `OpenAIChatWrapper`）
  - `agentscope.init()` 已在 2.0 移除

---

## 9. 业务层架构决策（2026-07-30 定稿）

### 9.1 订单与用户的关系
- 每个 C 端用户可以有**多个订单**（历史 + 进行中）
- "进行中"订单定义：status=pending 的最新一个
- Agent 工具只读写当前用户的订单，**不跨用户**（用 JWT 拿 user_id）

### 9.2 对话式下单工作流
1. 用户开始对话 → Agent 通过 `create_draft_order` 工具创建 draft 订单
2. Agent 主动询问：项目 / 发型师 / 时间 / 电话
3. 用户每次回复 → Agent 用 `update_order_fields` 工具更新对应字段
4. 用户说"不知道做什么" → Agent 调用 `recommend_services` 工具给出推荐
5. 所有必填字段就绪 → Agent 提示用户"是否确认下单"
6. 用户确认 → Agent 调用 `confirm_order`，订单 status 变 pending（店家后台可见）

### 9.3 Agent 工具集
| 工具名 | 作用 |
|--------|------|
| `create_draft_order` | 初始化一个 draft 订单，绑定当前 user_id |
| `update_order_fields` | 增量更新订单字段（服务/发型师/时间/电话/备注） |
| `recommend_services` | 根据用户需求（场合/发质/预算）推荐服务项目 |
| `list_stylists` | 列出可选发型师 |
| `confirm_order` | 用户确认后，把 draft 订单切到 pending 状态 |

### 9.4 必填字段
- service_type（服务项目）
- stylist_id（发型师，**必填**，不指定发型师不让下单）
- appointment_date + appointment_time（预约时间）
- customer_phone（联系电话）

非必填：address、note

### 9.5 后端业务层接口清单
| 方法 | 路径 | 用途 |
|------|------|------|
| GET    | /api/stylists | 列出可用发型师（公开） |
| GET    | /api/services | 列出可用服务（公开） |
| GET    | /api/orders | 当前用户订单列表（需鉴权） |
| GET    | /api/orders/{id} | 订单详情 |
| POST   | /api/orders | 直接下单（非对话场景） |
| PATCH  | /api/orders/{id}/status | 店家改订单状态 |
| POST   | /api/orders/{id}/cancel | 用户取消订单 |

