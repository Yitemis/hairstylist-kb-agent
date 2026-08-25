# -*- coding: utf-8 -*-
"""Booking Agent (P1-8: 6 个 booking 工具真被 Agent 接管).

之前: 6 个工具只注册了 1 个被 Agent 调, 其余 5 个被手写 if-else 调.
现在: 6 个 booking 工具全部装到 Agent.

P1: 接入 StuckLoopDetector 防 LLM 抽风死循环 (借鉴 WeKnora §5.4)
"""
from __future__ import annotations

import asyncio
import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model
from app.core.stuck_loop_detector import StuckLoopDetector
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_BOOKING_SYSTEM_PROMPT = """你是**美发预约助手**, 帮用户一步步完成预约订单.

## 工作流 (你必须严格按顺序引导)
1. 第一步必须调 create_draft_order(user_id) 创建草稿订单
2. 第二步调 list_branches(user_id, user_latitude=?, user_longitude=?) 列出分店
3. 用户选了分店 -> 调 update_order_fields 更新 branch_id
4. 用户选完分店 -> 调 list_stylists(user_id, branch_id) 列出发型师
5. 用户选了发型师 -> 调 update_order_fields 更新 stylist_id
6. 用户不知道选什么项目 -> 调 recommend_services(user_id, 用户需求)
7. 用户选完项目 -> 询问日期时间, 电话, 姓名, 逐一调 update_order_fields 更新
8. 所有必填信息齐全 -> 调 confirm_order(user_id, order_id) 确认
9. 用户想取消已存在的订单 -> 调 cancel_order(user_id, order_id, reason=?)

## 规则
- 每步只调一个工具
- 所有工具调用必须带 user_id 参数
- 工具返回错误时, 把错误信息告诉用户让其重选
- confirm_order / cancel_order 是高危操作, 工具内部会触发用户二次确认 (返回 ask_id)
"""


# ============================================================
# P1: StuckLoop 检测 (Booking Agent 专用 - booking 工具会反复尝试)
# ============================================================

def _wrap_reply_with_stuck_detection(agent, max_consecutive=3):
    """包装 agent.reply() 加 stuck loop 检测."""
    detector = StuckLoopDetector(max_consecutive=max_consecutive)
    original_reply = agent.reply

    async def safe_reply(messages, **kwargs):
        detector.reset()
        try:
            result = await original_reply(messages, **kwargs)

            content = _extract_content(result)
            if content and detector.check_content(content):
                logger.warning("BookingAgent StuckLoop: content stuck, breaking")
                return result

            tool_sig = _extract_tool_sig(result)
            if tool_sig:
                name, args = tool_sig
                if detector.check_tool_call(name, dict(args)):
                    logger.warning("BookingAgent StuckLoop: tool call stuck (%s), breaking", name)
                    return result

            return result
        except Exception as e:
            logger.error("BookingAgent reply failed: %s", e)
            raise

    return safe_reply


def _extract_content(chunk) -> str:
    if not chunk:
        return ""
    if hasattr(chunk, "content") and chunk.content:
        text = ""
        for block in chunk.content:
            if hasattr(block, "text") and block.text:
                text += block.text
        return text
    return ""


def _extract_tool_sig(chunk):
    if not chunk or not hasattr(chunk, "content"):
        return None
    for block in chunk.content:
        if hasattr(block, "name") and block.name:
            args = getattr(block, "input", None) or getattr(block, "arguments", None) or {}
            if isinstance(args, dict):
                return (block.name, args)
    return None


async def build_booking_agent(enable_stuck_detection=True) -> Agent:
    """构建 Booking Agent.

    工具装载: 6 个 booking 工具, 走 await toolkit.add_tool 官方 API.
    P1: 接入 StuckLoopDetector.
    """
    booking_tool_names = {
        "create_draft_order", "update_order_fields", "confirm_order",
        "cancel_order",
        "list_branches", "list_stylists", "recommend_services",
    }
    selected_tools = [t for t in registry.get_tools() if t.name in booking_tool_names]

    toolkit = Toolkit()
    for tool in selected_tools:
        await toolkit.add_tool(tool, group_name="basic")

    model = get_model("chat")
    agent = Agent(
        name="美发预约助手",
        system_prompt=_BOOKING_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )

    # P1: 注入 stuck loop 检测
    if enable_stuck_detection:
        agent.reply = _wrap_reply_with_stuck_detection(agent, max_consecutive=3)
        logger.info("Booking Agent 已注入 StuckLoopDetector")

    logger.info("Booking Agent 已构建: 工具=%d", len(selected_tools))
    return agent


_booking_agent_instance = None
_init_lock = asyncio.Lock()


async def get_booking_agent() -> Agent:
    """获取 Booking Agent 单例."""
    global _booking_agent_instance
    if _booking_agent_instance is None:
        async with _init_lock:
            if _booking_agent_instance is None:
                _booking_agent_instance = await build_booking_agent()
    return _booking_agent_instance


def reload_booking_agent() -> None:
    """热重载 Booking Agent."""
    global _booking_agent_instance
    _booking_agent_instance = None
