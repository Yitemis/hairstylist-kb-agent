# -*- coding: utf-8 -*-
"""Booking 状态机的边函数（条件路由）.

借鉴 JavaGuide §5.2 "Graph 三元素"：
- 顺序边：固定推进
- 条件边：根据 State 在候选路径选择
- 回边：节点回到自身或前序节点（重试 / 回退）
- 终止边：流程结束

借鉴 JavaGuide §5.5 "Loop 设计三要素"：
- 继续条件：为什么还要再来一轮
- 退出条件：什么时候已经足够好
- 安全边界：最大轮次 + 超时 + 熔断
"""
from __future__ import annotations

import logging
from typing import Literal

from app.rag.workflow.booking_parsers import detect_change_intent
from app.rag.workflow.booking_state import BookingState, BookingStep, CHECKIN_ORDER

logger = logging.getLogger(__name__)


# ============ 路由类型 ============

RouteDecision = Literal[
    "next",      # 推进到下一节点
    "retry",     # 重试当前节点（回边）
    "back",      # 回退到前一节点
    "aborted",   # 中止
    "end",       # 流程结束
    "draft",     # 进入草稿节点
    "checkin_branch",  # 跳到指定节点
    "checkin_service",
    "checkin_stylist",
    "checkin_datetime",
    "checkin_phone",
    "checkin_name",
    "confirm",
    "idle",      # 留在 idle 等用户
]


# ============ 顺序推进辅助 ============

def _next_step(current: BookingStep) -> str:
    """下一节点."""
    if current in CHECKIN_ORDER:
        idx = CHECKIN_ORDER.index(current)
        if idx == len(CHECKIN_ORDER) - 1:
            return "confirm"
        return CHECKIN_ORDER[idx + 1]
    if current == "draft":
        return "checkin_branch"
    return "aborted"


def _prev_step(current: BookingStep) -> str:
    """前一个节点."""
    if current in CHECKIN_ORDER:
        idx = CHECKIN_ORDER.index(current)
        if idx == 0:
            return "draft"
        return CHECKIN_ORDER[idx - 1]
    return "idle"


# ============ 边函数 1: route_after_idle ============

def route_after_idle(state: BookingState) -> str:
    """IDLE 节点后的路由.

    返回:
    - "draft"：用户说要预约
    - "intake"：已有订单 + 有 user_input，需要 intake 智能路由
    - "aborted"：用户在问别的问题（路由回主 Agent）
    - "end"：没 user_input 且不需要动作，退出等用户
    - "idle"：等用户继续输入
    - 其他：恢复到对应节点
    """
    # 没 user_input 且未进入流程 → 退出
    if not state.get("user_input", "").strip() and not state.get("order_id"):
        return "end"

    # 没 user_input 但有订单（恢复中） → intake
    if not state.get("user_input", "").strip() and state.get("order_id"):
        return "end"  # 等用户输入

    # 已有订单 + 有 user_input → 让 intake 决定是继续填、改字段、还是题外话
    if state.get("order_id") and state.get("user_input", "").strip():
        return "intake"

    step = state.get("current_step")
    if step == "draft":
        return "draft"
    if step == "aborted":
        return "aborted"
    if step in CHECKIN_ORDER:
        return step  # 恢复之前的状态
    return "idle"


# ============ 边函数 2: route_after_checkin（通用 CHECKIN 路由）============

def route_after_checkin(state: BookingState) -> str:
    """通用 CHECKIN 节点路由.

    决策逻辑：
    1. aborted → 路由回主 Agent
    2. needs_retry=True → end（等待用户重新输入，graph 退出）
    3. 用户说"换 XX" → 跳到对应节点
    4. current_step 是目标节点 → 直接路由过去
    5. 兜底 → end

    重要：节点返回时已设置 current_step = 目标节点名
         路由函数负责跳到那个节点
    """
    # 1. 中止
    if state.get("current_step") == "aborted":
        return "aborted"

    # 2. needs_retry → 退出等用户重新输入
    if state.get("needs_retry"):
        return "end"

    # 3. 用户说"换 XX" → 跳到对应节点
    user_input = state.get("user_input", "")
    target = detect_change_intent_sync(user_input)
    if target and target in CHECKIN_ORDER:
        return target

    # 4. current_step 是目标节点（节点自己设置的）
    current = state.get("current_step")
    if current in CHECKIN_ORDER:
        return current  # 直接路由到 current_step，不再自动 next

    # 5. 兜底 → end（避免无限循环）
    return "end"


def detect_change_intent_sync(user_input: str) -> str | None:
    """同步版 detect_change_intent（避免 await 在边函数里）.

    LangGraph 边函数默认是同步的。
    """
    if not user_input:
        return None
    text = user_input.strip()
    change_keywords = ["换", "改", "重新", "不是", "不对", "错了"]
    if not any(kw in text for kw in change_keywords):
        return None
    if "分店" in text or "店" in text:
        return "checkin_branch"
    if "项目" in text or "服务" in text or "烫" in text or "染" in text or "剪" in text:
        return "checkin_service"
    if "发型师" in text:
        return "checkin_stylist"
    if "时间" in text or "日期" in text or "几点" in text or "什么时候" in text:
        return "checkin_datetime"
    if "电话" in text or "手机" in text:
        return "checkin_phone"
    if "名字" in text or "姓名" in text:
        return "checkin_name"
    return None


# ============ 边函数 3: route_after_confirm ============

def route_after_confirm(state: BookingState) -> str:
    """CONFIRM 节点后的路由.

    返回:
    - "end"：成功，流程结束
    - "retry"：重试（待 HITL 确认）
    - "back"：用户说"等下"（回 checkin_name）
    - "aborted"：用户取消
    """
    if state.get("current_step") == "aborted":
        return "aborted"

    if state.get("needs_retry"):
        return "retry"  # 等 HITL

    if state.get("pending_ask_id"):
        return "retry"  # 等用户确认 HITL

    # 成功
    return "end"


# ============ 边函数 4: route_after_aborted ============

def route_after_aborted(state: BookingState) -> str:
    """ABORTED 节点后的路由.

    永远结束（路由回主 Agent）。
    """
    return "end"


# ============ 边函数 5: route_after_intake（Intake Router 后路由）============

def route_after_intake(state: BookingState) -> str:
    """Intake Router 后的路由.

    根据 pending_intent 决定去哪:
    - continue → 当前 step（继续填字段）
    - change_branch / change_service / ... → 跳到对应节点
    - cancel → aborted
    - side_question / query_status → end（已经给出 final_message，等下轮）

    重要：side_question 已经在节点内回答了，state.final_message 已设置
          不需要再回原 step 重复处理（user_input 也不该被原 step 重复解析）
    """
    intent = state.get("pending_intent", "continue")

    # 1. 取消 → aborted
    if intent == "cancel":
        return "aborted"

    # 2. 改字段 → 跳到对应节点
    change_map = {
        "change_branch": "checkin_branch",
        "change_service": "checkin_service",
        "change_stylist": "checkin_stylist",
        "change_datetime": "checkin_datetime",
        "change_phone": "checkin_phone",
        "change_name": "checkin_name",
    }
    if intent in change_map:
        return change_map[intent]

    # 3. 题外话 / 查询状态 → 节点内已回答, 退出等下轮
    if intent in ("side_question", "query_status"):
        return "end"

    # 4. continue → 当前 step
    current = state.get("current_step", "checkin_branch")
    if current in CHECKIN_ORDER or current in ("draft", "confirm", "idle"):
        return current

    # 5. 兜底
    return "checkin_branch"


__all__ = [
    "route_after_idle",
    "route_after_checkin",
    "route_after_confirm",
    "route_after_aborted",
    "route_after_intake",
    "_next_step",
    "_prev_step",
]
