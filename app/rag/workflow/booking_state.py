# -*- coding: utf-8 -*-
"""Booking 状态机的 State Schema.

借鉴 JavaGuide workflow-graph-loop.md §5.2 "Graph 三元素"：
- State 是节点间共享的"工作记忆"（键值对数据结构）
- 累积型字段用 Append，单值字段用 Replace
- 并行写入字段必须用自定义 Reducer

设计原则（参考 JavaGuide §5.5）：
- State 粒度按业务含义分块（输入 / 订单字段 / 流程控制 / 缓存 / 输出）
- 抽象"持久记住什么"，不写"调了哪个 API"
"""
from __future__ import annotations

import operator
from datetime import date, time
from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# ============ Step 字面量类型 ============

BookingStep = Literal[
    "idle",
    "draft",
    "checkin_branch",
    "checkin_service",
    "checkin_stylist",
    "checkin_datetime",
    "checkin_phone",
    "checkin_name",
    "confirm",
    "aborted",
]

CHECKIN_ORDER: tuple[BookingStep, ...] = (
    "checkin_branch",
    "checkin_service",
    "checkin_stylist",
    "checkin_datetime",
    "checkin_phone",
    "checkin_name",
)


# ============ State Schema ============

class BookingState(TypedDict, total=False):
    """Booking 状态机全局 State.

    分块（参考 JavaGuide §5.5）：
    1. 输入块（Append）：messages
    2. 订单字段块（Replace）：分店 / 服务 / 发型师 / 时间 / 客户信息
    3. 流程控制块（Replace）：current_step / iteration_count / last_error / needs_retry
    4. 工具上下文块（Replace）：最近工具调用 / 缓存
    5. 输出块（Replace）：final_message
    """

    # ========== 1. 输入块（Append 策略：累积） ==========
    messages: Annotated[list[BaseMessage], add_messages]
    """对话历史。LangGraph add_messages Reducer 会按 ID 去重/追加."""

    user_input: str
    """本轮用户输入（latest turn）."""

    # ========== 2. 订单字段块（Replace 策略：覆盖） ==========
    # 订单标识
    order_id: Optional[int]
    order_no: Optional[str]
    user_id: int

    # 分店
    branch_id: Optional[int]
    branch_name: Optional[str]

    # 服务
    service_id: Optional[int]
    service_type: Optional[str]
    service_details: Optional[str]
    duration_minutes: Optional[int]
    total_price: Optional[float]

    # 发型师
    stylist_id: Optional[int]
    stylist_name: Optional[str]

    # 时间
    appointment_date: Optional[str]  # ISO YYYY-MM-DD
    appointment_time: Optional[str]  # HH:MM
    end_time: Optional[str]           # HH:MM

    # 客户信息
    customer_phone: Optional[str]
    customer_name: Optional[str]
    note: Optional[str]

    # ========== 3. 流程控制块（Replace 策略） ==========
    current_step: BookingStep
    """当前所在的填字段阶段."""

    iteration_count: int
    """总迭代次数（防死循环的安全边界，参考 JavaGuide §5.3）."""

    max_iterations: int
    """最大允许迭代次数（默认 10）."""

    last_error: Optional[str]
    """最近一次工具调用错误（瞬时 / 校验失败）."""

    needs_retry: bool
    """是否需要重试当前节点."""

    # ========== 4. 工具上下文块（Replace 策略） ==========
    last_tool_call: Optional[dict[str, Any]]
    """最近一次工具调用（name + args + result）."""

    recommended_services: Optional[list[dict[str, Any]]]
    """recommend_services 返回的候选（缓存给用户看）."""

    branches_cache: Optional[list[dict[str, Any]]]
    """list_branches 缓存（避免重复查询）."""

    services_cache: Optional[list[dict[str, Any]]]
    """get_services_dict 缓存（避免重复查询）."""

    stylists_cache: Optional[dict[str, list[dict[str, Any]]]]
    """list_stylists 缓存（按 branch_id str 索引）."""

    # ========== 5. 输出块（Replace 策略） ==========
    final_message: Optional[str]
    """最终给用户看的回复文本."""

    pending_ask_id: Optional[str]
    """HITL 询问 ID（confirm_order 需要人工确认时设置）."""

    pending_intent: Optional[str]
    """Intake Router 识别的意图（用于跨节点传递）."""

    side_answer: Optional[str]
    """题外话的回答（side_question 时设置）."""

    status_text: Optional[str]
    """查询状态时的状态文本（query_status 时设置）."""


# ============ 工厂：构造初始 State ============

def make_initial_state(
    user_id: int,
    user_input: str = "",
    max_iterations: int = 10,
) -> BookingState:
    """构造初始 State.

    Args:
        user_id: 当前登录用户 ID
        user_input: 用户本轮输入
        max_iterations: 最大迭代次数（默认 10）

    Returns:
        初始化的 BookingState
    """
    return BookingState(
        messages=[],
        user_input=user_input,
        order_id=None,
        order_no=None,
        user_id=user_id,
        branch_id=None,
        branch_name=None,
        service_id=None,
        service_type=None,
        service_details=None,
        duration_minutes=None,
        total_price=None,
        stylist_id=None,
        stylist_name=None,
        appointment_date=None,
        appointment_time=None,
        end_time=None,
        customer_phone=None,
        customer_name=None,
        note=None,
        current_step="idle",
        iteration_count=0,
        max_iterations=max_iterations,
        last_error=None,
        needs_retry=False,
        last_tool_call=None,
        recommended_services=None,
        branches_cache=None,
        services_cache=None,
        stylists_cache=None,
        final_message=None,
        pending_ask_id=None,
        pending_intent=None,
        side_answer=None,
        status_text=None,
    )


# ============ 辅助：判断是否完成所有必填字段 ============

REQUIRED_FIELDS = (
    "branch_id",
    "service_type",
    "stylist_id",
    "appointment_date",
    "appointment_time",
    "duration_minutes",
    "customer_phone",
)


_FIELD_CN = {
    "branch_id": "分店",
    "service_type": "服务项目",
    "stylist_id": "发型师",
    "appointment_date": "预约日期",
    "appointment_time": "预约时间",
    "duration_minutes": "服务时长",
    "customer_phone": "联系电话",
}


def get_missing_required_fields(state: BookingState) -> list[str]:
    """返回还未填的必填字段名.

    Returns:
        字段名列表（中文）
    """
    return [_FIELD_CN[f] for f in REQUIRED_FIELDS if not state.get(f)]


__all__ = [
    "BookingState",
    "BookingStep",
    "CHECKIN_ORDER",
    "make_initial_state",
    "get_missing_required_fields",
    "REQUIRED_FIELDS",
]
