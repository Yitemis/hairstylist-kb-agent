# -*- coding: utf-8 -*-
"""Booking 状态机组装.

借鉴 JavaGuide workflow-graph-loop.md §5 "代码实现"：
- Spring AI Alibaba / LangGraph 都是这套思路
- 节点只做一件事
- 边函数决定路由
- State 共享上下文

借鉴 JavaGuide §5.6 "持久化"：
- MemorySaver / SqliteSaver / PostgresSaver
- 我们用 MemorySaver（开发）/ PostgresSaver（生产）
"""
from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.rag.workflow.booking_edges import (
    route_after_aborted,
    route_after_checkin,
    route_after_confirm,
    route_after_idle,
    route_after_intake,
)
from app.rag.workflow.booking_nodes import (
    node_aborted,
    node_checkin_branch,
    node_checkin_datetime,
    node_checkin_name,
    node_checkin_phone,
    node_checkin_service,
    node_checkin_stylist,
    node_confirm,
    node_draft,
    node_idle,
    node_intake_router,
)
from app.rag.workflow.booking_state import (
    CHECKIN_ORDER,
    BookingState,
    BookingStep,
    make_initial_state,
)

logger = logging.getLogger(__name__)


# ============ Graph 工厂 ============

def build_booking_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> StateGraph:
    """构建 Booking 状态机.

    Args:
        checkpointer: 检查点保存器（开发 MemorySaver，生产 PostgresSaver）

    Returns:
        编译后的 StateGraph
    """
    workflow = StateGraph(BookingState)

    # ========== 1. 添加节点 ==========
    workflow.add_node("idle", node_idle)
    workflow.add_node("intake", node_intake_router)  # 智能路由（题外话、改字段、取消等）
    workflow.add_node("draft", node_draft)
    workflow.add_node("checkin_branch", node_checkin_branch)
    workflow.add_node("checkin_service", node_checkin_service)
    workflow.add_node("checkin_stylist", node_checkin_stylist)
    workflow.add_node("checkin_datetime", node_checkin_datetime)
    workflow.add_node("checkin_phone", node_checkin_phone)
    workflow.add_node("checkin_name", node_checkin_name)
    workflow.add_node("confirm", node_confirm)
    workflow.add_node("aborted", node_aborted)

    # ========== 2. 入口边 ==========
    workflow.add_edge(START, "idle")

    # ========== 3. 顺序边 ==========
    # DRAFT → CHECKIN_BRANCH（无需条件，无脑推进）
    workflow.add_edge("draft", "checkin_branch")

    # ========== 4. 条件边 ==========
    # IDLE 节点（开始/中止/恢复）→ 先过 intake 路由
    workflow.add_conditional_edges(
        "idle",
        route_after_idle,
        {
            "draft": "draft",
            "aborted": "aborted",
            "intake": "intake",  # 经过 intake 路由
            "checkin_branch": "checkin_branch",
            "checkin_service": "checkin_service",
            "checkin_stylist": "checkin_stylist",
            "checkin_datetime": "checkin_datetime",
            "checkin_phone": "checkin_phone",
            "checkin_name": "checkin_name",
            "confirm": "confirm",
            "end": END,
        },
    )

    # 所有 CHECKIN 节点都走通用路由
    _add_checkin_edges(workflow, "checkin_branch")
    _add_checkin_edges(workflow, "checkin_service")
    _add_checkin_edges(workflow, "checkin_stylist")
    _add_checkin_edges(workflow, "checkin_datetime")
    _add_checkin_edges(workflow, "checkin_phone")
    _add_checkin_edges(workflow, "checkin_name")

    # Intake 节点（智能路由）
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "checkin_branch": "checkin_branch",
            "checkin_service": "checkin_service",
            "checkin_stylist": "checkin_stylist",
            "checkin_datetime": "checkin_datetime",
            "checkin_phone": "checkin_phone",
            "checkin_name": "checkin_name",
            "aborted": "aborted",
            "end": END,
        },
    )

    # CONFIRM 节点（end/retry/back/aborted）
    workflow.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {
            "end": END,
            "retry": "confirm",
            "back": "checkin_name",
            "aborted": "aborted",
        },
    )

    # ABORTED 节点（end）
    workflow.add_conditional_edges(
        "aborted",
        route_after_aborted,
        {"end": END},
    )

    # ========== 5. 编译 ==========
    if checkpointer is None:
        checkpointer = MemorySaver()
        logger.info("Booking graph using MemorySaver (development)")

    return workflow.compile(checkpointer=checkpointer)


def _add_checkin_edges(workflow: StateGraph, node_name: str) -> None:
    """给 CHECKIN 节点加条件边."""
    next_node = _next_of(node_name)

    routing_map: dict[str, str] = {
        "next": next_node,
        "retry": node_name,  # 回边：重试自己
        "aborted": "aborted",
        "end": END,  # 等用户输入后退出
    }

    # back 边：回到前一节点
    prev_node = _prev_of(node_name)
    if prev_node:
        routing_map["back"] = prev_node

    # 用户说"换 XX" 时，目标节点（detect_change_intent_sync 返回的）
    # 其他 CHECKIN 节点都可能成为目标
    for step in CHECKIN_ORDER:
        if step != node_name:
            routing_map[step] = step

    workflow.add_conditional_edges(
        node_name,
        route_after_checkin,
        routing_map,
    )


def _next_of(current: str) -> str:
    """当前节点的下一节点."""
    if current in CHECKIN_ORDER:
        idx = CHECKIN_ORDER.index(current)
        if idx == len(CHECKIN_ORDER) - 1:
            return "confirm"
        return CHECKIN_ORDER[idx + 1]
    return "confirm"


def _prev_of(current: str) -> str | None:
    """当前节点的前一节点."""
    if current in CHECKIN_ORDER:
        idx = CHECKIN_ORDER.index(current)
        if idx == 0:
            return "draft"
        return CHECKIN_ORDER[idx - 1]
    return None


# ============ 全局单例 ============

_graph_instance: Optional[StateGraph] = None


def get_booking_graph() -> StateGraph:
    """获取全局 Booking Graph 单例."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_booking_graph()
        logger.info("Booking graph initialized (singleton)")
    return _graph_instance


def reset_booking_graph() -> None:
    """重置 Graph（测试用）."""
    global _graph_instance
    _graph_instance = None


# ============ 便捷调用入口 ============

async def run_booking_turn(
    user_id: int,
    session_id: str,
    user_input: str,
    state: Optional[BookingState] = None,
) -> BookingState:
    """跑一轮 booking 对话.

    Args:
        user_id: 当前用户 ID
        session_id: 会话 ID（用作 thread_id 持久化）
        user_input: 本轮用户输入
        state: 已有的 state（不传则用初始 state）

    Returns:
        跑完一轮后的完整 state

    行为：
    - 用 thread_id 持久化 state (MemorySaver)
    - 第二轮会自动从上次中断的节点继续
    """
    graph = get_booking_graph()
    config = {"configurable": {"thread_id": session_id}}

    # 准备输入 - 只传 user_input, 不要传完整 state
    # LangGraph 会自动从 MemorySaver 加载历史 state 并 merge
    # 第一次调用时 state 是空的, 后续会自动恢复
    # 关键: 把 user_input 清空（避免上轮的 user_input 污染这轮）
    input_state = {
        "user_id": user_id,
        "user_input": user_input,
    }
    if state is not None:
        # 显式传了 state 的话, merge
        input_state = {**state, **input_state}

    # 关键修复：清空 state 里的 user_input, 用本轮新的
    # （MemorySaver 持久化的 state 可能有上轮的 user_input）
    input_state["user_input"] = user_input

    # 调用 graph
    result = await graph.ainvoke(input_state, config=config)
    logger.info(
        "run_booking_turn result: user=%d step=%s order=%d",
        user_id, result.get("current_step"), result.get("order_id"),
    )
    return result


__all__ = [
    "build_booking_graph",
    "get_booking_graph",
    "reset_booking_graph",
    "run_booking_turn",
]
