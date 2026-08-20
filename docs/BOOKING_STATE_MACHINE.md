# Booking 流程 LangGraph 状态机设计

> 基于 JavaGuide `workflow-graph-loop.md` 实战经验
> 对应我们 `app/core/tools/order_tools.py` 的 6 个工具
> 关联文档：[AGENT_DEVELOPMENT_PLAYBOOK.md §3 L3](AGENT_DEVELOPMENT_PLAYBOOK.md)

---

## 1. 为什么 booking 必须用 LangGraph

我们 booking 流程的 6 个工具 + 7 个必填字段 + 13 个总字段，**强结构**：

| 维度 | 数值 |
|------|------|
| 工具数 | 6（`create_draft_order` / `update_order_fields` / `confirm_order` / `list_branches` / `list_stylists` / `recommend_services`） |
| 必填字段 | 7（branch_id, service_type, stylist_id, appointment_date, appointment_time, duration_minutes, customer_phone） |
| 可选字段 | 6（service_id, service_details, customer_name, address, note, total_price） |
| 业务流程 | 强序列：分店 → 服务 → 发型师 → 时间 → 电话 → 姓名 → 确认 |

**两种范式对比**：

| | 硬编码 if-else（当前） | 纯 ReAct | **LangGraph 状态机** |
|---|---|---|---|
| 流程稳定性 | ✅ | ❌ 11 步每步重规划 | ✅ |
| 调试可观测 | ❌ | ❌ 黑盒 | ✅ 节点 + 边可视化 |
| 自然语言解析 | ❌ | ✅ 但浪费 Token | ✅ **局部 ReAct 解析** |
| 工具失败恢复 | ❌ 报错给用户 | ⚠️ 重新生成 | ✅ **状态可回退** |
| Pause/Resume | ❌ | ❌ | ✅ 持久化 checkpoint |
| 多人协作 | ❌ | ⚠️ | ✅ Graph 可视化 |

**结论**：**Agentic Workflows** —— 全局 Workflow（状态机）+ 局部 ReAct（解析自然语言）。

---

## 2. 状态机全景图

```text
                        ┌─────────┐
                        │  START  │
                        └────┬────┘
                             ↓
                       ┌───────────┐
                  ┌───→│   IDLE    │←──────────┐
                  │    │ 等待开始  │            │
                  │    └─────┬─────┘            │
                  │          ↓                 │
                  │    ┌─────────────┐         │
                  │    │  DRAFT      │ 创建草稿 │
                  │    └─────┬───────┘         │
                  │          ↓                 │
                  │    ┌─────────────┐         │
                  │    │ CHECKIN_    │ 选分店   │ 用户说"换一家"
                  │    │ BRANCH      ├─────────┘
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CHECKIN_    │ 选服务   │ (可省略: 用户用 recommend)
                  │    │ SERVICE     │
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CHECKIN_    │ 选发型师 │
                  │    │ STYLIST     │
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CHECKIN_    │ 选时间   │ (可能改日期)
                  │    │ DATETIME    │
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CHECKIN_    │ 留电话   │
                  │    │ PHONE       │
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CHECKIN_    │ 留姓名   │ (可选)
                  │    │ NAME        │
                  │    └─────┬───────┘
                  │          ↓
                  │    ┌─────────────┐
                  │    │ CONFIRM     │ 确认下单 │
                  │    └─────┬───────┘
                  │          ↓
                        ┌─────┴────┐
                        │   END    │
                        └──────────┘

    用户取消/异常 → ABORT
    任何节点可 → BACK_TO_*: 用户改主意，回到任意前面节点
```

**8 个核心节点 + 3 个边类型**：
- **顺序边**：CHECKIN_X → CHECKIN_Y（自然推进）
- **条件边**：用户说"换发型师" → 回到 `CHECKIN_STYLIST`
- **回边**：用户说"时间不对" → 回到 `CHECKIN_DATETIME`
- **终止边**：`CONFIRM` 成功 → `END`；用户取消 → `ABORT`

---

## 3. State Schema（Graph State）

```python
# app/rag/workflow/booking_state.py
from typing import Annotated, Any, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from operator import add

# ============ State 字段设计 ============

class BookingState(TypedDict):
    """Booking 状态机全局 State."""

    # ========== 输入（Append 策略：累积） ==========
    messages: Annotated[list, add_messages]
    """对话历史。LLM 看不到完整历史，只看到当前轮。

    注意：这里 add_messages 是 LangGraph Reducer，会自动按 ID 去重/追加。
    """

    user_input: str
    """本轮用户输入（latest turn）."""

    # ========== 订单字段（Replace 策略：覆盖） ==========
    order_id: Optional[int]
    order_no: Optional[str]
    user_id: int

    branch_id: Optional[int]
    branch_name: Optional[str]  # 缓存方便显示

    service_id: Optional[int]
    service_type: Optional[str]  # 自由文本
    service_details: Optional[str]
    duration_minutes: Optional[int]
    total_price: Optional[float]

    stylist_id: Optional[int]
    stylist_name: Optional[str]

    appointment_date: Optional[str]  # YYYY-MM-DD
    appointment_time: Optional[str]  # HH:MM
    end_time: Optional[str]           # HH:MM

    customer_phone: Optional[str]
    customer_name: Optional[str]
    note: Optional[str]

    # ========== 流程控制（Replace 策略） ==========
    current_step: Literal[
        "idle", "draft", "checkin_branch", "checkin_service",
        "checkin_stylist", "checkin_datetime", "checkin_phone",
        "checkin_name", "confirm", "aborted"
    ]
    """当前所在的填字段阶段.

    边函数读这个字段决定下一步去哪。
    """

    iteration_count: int
    """总迭代次数（防止死循环的安全边界）."""

    last_error: Optional[str]
    """最近一次工具调用错误（瞬时错误 / 校验失败）."""

    needs_retry: bool
    """是否需要重试当前节点（工具失败 / 解析失败）."""

    # ========== 工具调用上下文 ==========
    last_tool_call: Optional[dict]
    """最近一次工具调用（name + args + result），用于 Observation 写入."""

    recommended_services: Optional[list[dict]]
    """recommend_services 返回的候选服务（缓存给用户看）."""

    branches_cache: Optional[list[dict]]
    """list_branches 缓存（避免重复查询）."""

    stylists_cache: Optional[dict[int, list[dict]]]
    """list_stylists 缓存（按 branch_id 索引）."""

    # ========== 输出 ==========
    final_message: Optional[str]
    """最终给用户看的回复文本."""
```

**State 字段的更新策略**（参考 JavaGuide §5.2）：

| 字段 | 策略 | 理由 |
|------|------|------|
| `messages` | Append（`add_messages`） | 累积历史 |
| `order_id` / `branch_id` 等订单字段 | Replace | 单值 |
| `current_step` | Replace | 控制流 |
| `iteration_count` | Replace | 计数 |
| `last_error` | Replace | 单值 |
| `branches_cache` | Replace | 整体替换（不要追加） |

**注意并行写入竞态**：如果未来加入并行节点（如同时检索分店 + 发型师），涉及 `Replace` 策略的字段要小心。**目前我们的 booking 是纯顺序图，不存在竞态**。

---

## 4. Node 设计（8 个核心节点）

### 4.1 节点抽象接口

```python
# app/rag/workflow/booking_nodes.py
from typing import Any
from langgraph.runtime import Runtime
from app.rag.workflow.booking_state import BookingState


async def node_idle(state: BookingState, runtime: Runtime) -> dict:
    """IDLE 节点：等待用户开始预约.

    行为：
    - 用户说"我要预约" → 返回 DRAFT 节点
    - 用户问"怎么预约" → 解释流程 + 保持 IDLE
    - 用户问其他事 → aborted（路由回主 Agent 处理）
    """
    pass


async def node_draft(state: BookingState, runtime: Runtime) -> dict:
    """DRAFT 节点：创建草稿订单.

    行为：
    - 调 create_draft_order(user_id)
    - 拿到 order_id + order_no
    - 进入 CHECKIN_BRANCH
    """
    pass


async def node_checkin_branch(state: BookingState, runtime: Runtime) -> dict:
    """CHECKIN_BRANCH 节点：选分店.

    行为：
    1. 如果 state.branch_id 为空：调 list_branches 展示选项
    2. 用 LLM 解析用户自然语言（"最近的那家" → 经纬度最近的）
    3. 调 update_order_fields 写入 branch_id
    4. 进入 CHECKIN_SERVICE
    """
    pass
```

### 4.2 节点的 4 个标准阶段

**借鉴 JavaGuide §5.5 的"Node 抽象职责边界"原则**：每个 Node 只做"产出"什么，不写死"调了哪个 API"。

每个节点都遵循这个模板：

```python
async def node_checkin_x(state: BookingState, runtime: Runtime) -> dict:
    # ========== Phase 1: Detect（检测是否需要问用户）==========
    if state.field_x is not None:
        # 已经填过了 → 跳过
        return {"current_step": "checkin_y"}

    # ========== Phase 2: Prepare（准备展示数据）==========
    if not state.cache_for_x:
        data = await call_tool_list_x()
        return {
            "cache_for_x": data,  # 缓存
            "messages": [AIMessage(content=format_options(data))],
            "current_step": "checkin_x",  # 停留等用户输入
        }

    # ========== Phase 3: Parse（局部 ReAct 解析用户输入）==========
    parsed = await local_react_parse(
        user_input=state.user_input,
        field="x",
        candidates=state.cache_for_x,
    )
    if not parsed:
        return {
            "last_error": "我没理解你的选择，请再说一次",
            "needs_retry": True,
        }

    # ========== Phase 4: Update（调工具写入 + 推进）==========
    result = await update_order_fields(
        user_id=state["user_id"],
        order_id=state["order_id"],
        **{f"{field}_id": parsed["id"]},
    )
    return {
        f"{field}_id": parsed["id"],
        f"{field}_name": parsed["name"],
        "current_step": "checkin_y",
        "needs_retry": False,
        "last_error": None,
        "messages": [AIMessage(content=result)],
    }
```

### 4.3 每个节点的特殊处理

| 节点 | 特殊点 |
|------|--------|
| **IDLE** | 意图识别：用户真要预约还是闲聊？闲聊 → `aborted` 路由回主 Agent |
| **DRAFT** | 调 `create_draft_order`，需要 LLM 提取 user_id |
| **CHECKIN_BRANCH** | 可按用户位置排序（Haversine）；用户说"人民广场" → 解析分店名 |
| **CHECKIN_SERVICE** | 可选跳过（用户说"你帮我推荐" → 调 `recommend_services`） |
| **CHECKIN_STYLIST** | 依赖 branch_id（必须先选分店才能选发型师） |
| **CHECKIN_DATETIME** | 解析"明天下午 3 点" → `appointment_date=YYYY-MM-DD` + `appointment_time=15:00` |
| **CHECKIN_PHONE** | 校验手机号格式（11 位 / 1开头） |
| **CHECKIN_NAME** | **可选** —— 用户说"姓名 X" 填，否则跳过 |
| **CONFIRM** | HITL 检查 + 三重冲突检查 + 调 `confirm_order` |

---

## 5. 边函数（条件路由）

```python
# app/rag/workflow/booking_edges.py
from app.rag.workflow.booking_state import BookingState


def route_after_idle(state: BookingState) -> str:
    """IDLE 节点之后的路由."""
    if state["current_step"] == "aborted":
        return "aborted"  # 路由回主 Agent
    if state["current_step"] == "draft":
        return "draft"
    return "idle"  # 继续等用户


def route_after_checkin_x(state: BookingState) -> str:
    """通用 CHECKIN 节点路由.

    返回: "next" / "retry" / "back" / "aborted"
    """
    if state["needs_retry"]:
        return "retry"  # 重试当前节点（回边）
    if state["current_step"] == "aborted":
        return "aborted"
    # 用户说"换发型师" → back
    if detect_user_wants_to_change(state["user_input"]):
        return "back"
    return "next"  # 推进到下一节点


def detect_user_wants_to_change(user_input: str) -> bool:
    """LLM 判断用户是否想改前面的字段.

    比如"等下我想换发型师" → 应该回到 CHECKIN_STYLIST 而不是 CHECKIN_DATETIME。
    """
    # 简单实现：关键词 + LLM 分类
    change_keywords = ["换", "改", "重新", "不是", "不对"]
    return any(kw in user_input for kw in change_keywords)
```

**边的类型**（参考 JavaGuide §5.2）：
- **顺序边**：`IDLE → DRAFT → CHECKIN_BRANCH → ...`
- **条件边**：`route_after_checkin_x` 函数决定 next / retry / back
- **回边**：retry 边回到当前节点；back 边回到前一节点
- **终止边**：`CONFIRM` 成功 → `END`；`aborted` → 路由回主 Agent

---

## 6. 局部 ReAct 解析（Node 内部）

每个 CHECKIN 节点内部都有一个**局部 ReAct** 用于解析自然语言：

```python
# app/rag/workflow/booking_parsers.py
from app.core.model_factory import get_model
from agentscope.message import TextBlock, UserMsg


async def parse_branch_choice(
    user_input: str,
    branches: list[dict],
) -> dict | None:
    """局部 ReAct: 从用户输入里提取分店选择.

    Examples:
        "人民广场那家" → {"id": 2, "name": "人民广场店"}
        "最近的那家" → 需要用户位置, 让上游传
        "换一家吧" → 返回 None（不更新, 让外层路由）
    """
    model = get_model("chat")

    branches_text = "\n".join(
        f"[{b['id']}] {b['name']}（{b['address']}）"
        for b in branches
    )

    prompt = f"""从用户输入里提取分店选择.

可选分店:
{branches_text}

用户输入: "{user_input}"

如果用户明确选了某家, 输出 JSON: {{"id": 数字, "name": "店名"}}
如果用户没明确选（比如在问问题或要换店），输出: null

只输出 JSON, 不要其他解释."""

    try:
        resp = await model([UserMsg(content=prompt)])
        text = _extract_text(resp)
        if "null" in text.lower():
            return None
        import json, re
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        logger.warning("parse_branch_choice failed: %s", e)
    return None


async def parse_datetime(
    user_input: str,
    today_iso: str,
) -> dict | None:
    """局部 ReAct: 解析日期时间.

    Examples:
        "明天下午 3 点" → {"date": "2026-08-20", "time": "15:00"}
        "下周六上午 10:30" → {"date": "2026-08-22", "time": "10:30"}
        "8 月 25 号 14:00" → {"date": "2026-08-25", "time": "14:00"}
    """
    model = get_model("chat")

    prompt = f"""从用户输入里提取预约日期和时间.

今天日期: {today_iso}

用户输入: "{user_input}"

输出 JSON:
- date: YYYY-MM-DD 格式
- time: HH:MM 格式（24 小时制）

只输出 JSON, 不要其他解释.

如果无法解析, 输出: null"""

    # ... 同上 extract + parse
```

**为什么是"局部 ReAct"而不是"Agent Loop"**：
- 这里**任务非常窄**：从自然语言里提取结构化字段
- 不需要工具调用（LLM 自己能做）
- 不需要多轮推理
- 用 1 次 LLM 调用就够

> 这就是 JavaGuide §1.1 说的 **Agentic Workflows**："全局 Workflow + 局部 Agent 子循环"。

---

## 7. Graph 组装（核心代码）

```python
# app/rag/workflow/booking_graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver  # 持久化

from app.rag.workflow.booking_state import BookingState
from app.rag.workflow.booking_nodes import (
    node_idle, node_draft,
    node_checkin_branch, node_checkin_service, node_checkin_stylist,
    node_checkin_datetime, node_checkin_phone, node_checkin_name,
    node_confirm, node_aborted,
)
from app.rag.workflow.booking_edges import (
    route_after_idle, route_after_checkin, route_after_confirm,
)


def build_booking_graph(checkpointer=None) -> StateGraph:
    """构建 Booking 状态机."""

    workflow = StateGraph(BookingState)

    # ========== 添加节点 ==========
    workflow.add_node("idle", node_idle)
    workflow.add_node("draft", node_draft)
    workflow.add_node("checkin_branch", node_checkin_branch)
    workflow.add_node("checkin_service", node_checkin_service)
    workflow.add_node("checkin_stylist", node_checkin_stylist)
    workflow.add_node("checkin_datetime", node_checkin_datetime)
    workflow.add_node("checkin_phone", node_checkin_phone)
    workflow.add_node("checkin_name", node_checkin_name)
    workflow.add_node("confirm", node_confirm)
    workflow.add_node("aborted", node_aborted)

    # ========== 顺序边 ==========
    workflow.add_edge(START, "idle")
    workflow.add_edge("draft", "checkin_branch")
    workflow.add_edge("checkin_branch", "checkin_service")
    workflow.add_edge("checkin_service", "checkin_stylist")
    workflow.add_edge("checkin_stylist", "checkin_datetime")
    workflow.add_edge("checkin_datetime", "checkin_phone")
    workflow.add_edge("checkin_phone", "checkin_name")
    workflow.add_edge("checkin_name", "confirm")

    # ========== 条件边 ==========
    # IDLE 节点路由（开始 or aborted）
    workflow.add_conditional_edges(
        "idle",
        route_after_idle,
        {
            "draft": "draft",
            "aborted": "aborted",
            "idle": "idle",  # 循环等用户
        }
    )

    # CHECKIN 节点通用路由（next / retry / back / aborted）
    for node_name in [
        "checkin_branch", "checkin_service", "checkin_stylist",
        "checkin_datetime", "checkin_phone", "checkin_name",
    ]:
        workflow.add_conditional_edges(
            node_name,
            route_after_checkin,
            {
                "next": _next_node(node_name),  # 推进
                "retry": node_name,             # 回边：重试
                "back": _prev_node(node_name),  # 回边：回退
                "aborted": "aborted",
            }
        )

    # CONFIRM 节点路由（end or retry）
    workflow.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {
            "end": END,
            "retry": "confirm",
            "back": "checkin_name",  # 让用户改信息
        }
    )

    # ========== 编译 ==========
    return workflow.compile(checkpointer=checkpointer)


# ========== 节点推进辅助 ==========

CHECKIN_ORDER = [
    "checkin_branch", "checkin_service", "checkin_stylist",
    "checkin_datetime", "checkin_phone", "checkin_name",
]


def _next_node(current: str) -> str:
    idx = CHECKIN_ORDER.index(current)
    if idx == len(CHECKIN_ORDER) - 1:
        return "confirm"
    return CHECKIN_ORDER[idx + 1]


def _prev_node(current: str) -> str:
    idx = CHECKIN_ORDER.index(current)
    if idx == 0:
        return "idle"  # 回到最开始
    return CHECKIN_ORDER[idx - 1]
```

---

## 8. 与现有 booking_agent 的对比

| 维度 | 当前 `booking_agent_factory.py` | 新 LangGraph 状态机 |
|------|--------------------------------|---------------------|
| **入口** | AgentScope Agent + 6 tools | LangGraph StateGraph |
| **流程** | 写在 system prompt 文字里 | Node + Edge 显式建模 |
| **顺序保证** | ❌ 靠 LLM 自觉 | ✅ 顺序边强制 |
| **可观测** | ❌ 只能看 LLM 生成的 tool_call | ✅ 每个节点可埋点 |
| **回退** | ❌ 用户说"换发型师"容易跑偏 | ✅ 显式 back 边 |
| **错误恢复** | ❌ 工具失败报错 | ✅ state.last_error 走 retry 边 |
| **持久化** | ❌ 重启失忆 | ✅ PostgresSaver（Phase 1 P0-5 已有 Redis state_store，可对接） |
| **HITL** | ❌ 部分接了 | ✅ CONFIRM 节点内集中处理 |
| **SSE 事件** | ⚠️ 简陋 | ✅ 每个节点 emit AgentEvent（28 种） |

---

## 9. 与 chat 端点的集成

```python
# app/server/routers/chat_stream.py（伪代码）
from app.rag.workflow.booking_graph import build_booking_graph

# 启动时构建 Graph（全局单例）
_booking_graph = None

def get_booking_graph():
    global _booking_graph
    if _booking_graph is None:
        from app.rag.workflow.checkpointer import get_checkpointer
        _booking_graph = build_booking_graph(checkpointer=get_checkpointer())
    return _booking_graph


async def handle_booking_turn(
    user_id: int,
    session_id: str,
    user_input: str,
    current_state: BookingState,
) -> BookingState:
    """处理一轮 booking 对话."""

    graph = get_booking_graph()

    # 准备输入（合并 user_input 到 state）
    input_state = {
        **current_state,
        "user_id": user_id,
        "messages": [HumanMessage(content=user_input)],
    }

    # 调用 graph（thread_id 持久化）
    config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(input_state, config=config)

    return result
```

**关键点**：
- `thread_id = session_id`：每个会话一个独立 Graph 实例（自动隔离）
- `ainvoke` 自动从 checkpointer 恢复历史 state
- 用户跨天再来 → state 还在 → 接着填字段

---

## 10. 实施路线（Phase 1 子任务）

| 子任务 | 工期 | 文件 |
|--------|------|------|
| **1. 安装 LangGraph** | 0.5 天 | `requirements.txt` 加 `langgraph>=0.2` |
| **2. 写 State schema** | 0.5 天 | `app/rag/workflow/booking_state.py` |
| **3. 写 8 个 Node 骨架** | 2 天 | `app/rag/workflow/booking_nodes.py` |
| **4. 写 5 个 Parser（局部 ReAct）** | 1.5 天 | `app/rag/workflow/booking_parsers.py` |
| **5. 写 Edge 函数** | 0.5 天 | `app/rag/workflow/booking_edges.py` |
| **6. 写 Graph 组装 + Checkpointer** | 1 天 | `app/rag/workflow/booking_graph.py` |
| **7. 改 chat 端点用 Graph** | 1 天 | `app/server/routers/chat_stream.py` |
| **8. 端到端测试** | 1 天 | `tests/test_booking_state_machine.py` |
| **合计** | **8 天** | — |

**前置依赖**：
- ✅ `pybreaker`（熔断）— 已有
- ✅ `StuckLoopDetector`（死循环检测）— 已有，可作为 `iteration_count` 触发 break 的判断
- ⚠️ LangGraph 本身需要安装
- ⚠️ PostgresSaver 需要 `langgraph-checkpoint-postgres` + `psycopg` 驱动
- ⚠️ HITL 集成需要 `langgraph.prebuilt.interrupt_before`

---

## 11. 借鉴 JavaGuide 的关键决策

| 决策 | JavaGuide 建议 | 我们方案 |
|------|----------------|----------|
| **图框架选型** | Spring AI Alibaba / LangGraph | **LangGraph**（Python 生态更熟） |
| **State 更新策略** | 累积字段用 Append（`add_messages`），单值用 Replace | ✅ 按字段类型选 |
| **错误处理** | 4 类：瞬时 / LLM可恢复 / 用户可修复 / 意外 | ✅ `last_error` + `needs_retry` 走 retry 边 |
| **嵌套循环** | 内层（工具重试）独立于外层（质量迭代） | ✅ `iteration_count` + `max_iter=10` |
| **持久化** | MemorySaver / SqliteSaver / PostgresSaver | ✅ 对接 Phase 1 P0-5 已有 Redis state_store |
| **HITL** | `interruptBefore` + `updateState` | ✅ CONFIRM 节点用 `interrupt_before` |
| **Node 抽象** | 抽象"产出"而不是"调了哪个 API" | ✅ 4 个标准阶段（Detect/Prepare/Parse/Update） |
| **高风险操作自由度** | 改数据 → 自由度收紧 | ✅ CONFIRM 节点低自由度，写死 HITL |
| **State 粒度** | 按业务含义分块 | ✅ 4 块：订单字段 / 流程控制 / 缓存 / 输出 |

---

## 12. 不做 LangGraph 的代价

如果继续用 `booking_agent_factory.py`（AgentScope 纯 ReAct），会有 6 个长期问题：

1. **顺序靠 system prompt 文字约束** → 模型偶尔跳步（"我帮你直接确认了"）
2. **回退靠"重置 state"** → 字段可能丢
3. **错误恢复靠 LLM 自觉** → 工具失败后 LLM 经常瞎说
4. **持久化要自己写** → 重启会丢草稿
5. **HITL 是外挂的** → 与状态机脱节，状态不一致
6. **可视化 0** → 调试靠日志猜

> 上面 6 个问题，**LangGraph 全都解决了**。

---

## 📌 总结

| 项 | 现状 | 升级后 |
|----|------|--------|
| 范式 | AgentScope ReAct | **Agentic Workflows**（LangGraph + 局部 ReAct 解析） |
| 节点数 | 0（隐式 in prompt） | **8 个显式节点** |
| 边类型 | 0 | **顺序 + 条件 + 回边 + 终止** |
| State 字段 | 0（散落在 DB） | **20 个字段统一管理** |
| 持久化 | 0 | **PostgresSaver / 对接 Redis state_store** |
| 错误恢复 | ❌ | ✅ retry 边 |
| HITL | 半成品 | ✅ CONFIRM 节点内集中 |
| 工期 | — | **8 天** |
