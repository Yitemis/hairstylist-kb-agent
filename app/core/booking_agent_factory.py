# -*- coding: utf-8 -*-
"""Booking Agent (P1-8: 6 个 booking 工具真被 Agent 接管)。

之前: 6 个工具只注册了 1 个 (search_hair_knowledge) 被 Agent 调，其余 5 个被手写 if-else 调。
现在: 6 个 booking 工具全部装到 Agent，Agent 自主决定调哪个。

N7 修复: build_booking_agent 改 async + 用 await registry.build_toolkit() 官方 API。
"""
from __future__ import annotations

import asyncio
import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_BOOKING_SYSTEM_PROMPT = """你是**美发预约助手**，帮用户一步步完成预约订单。

## 工作流（你必须严格按顺序引导）
1. **第一步必须调 `create_draft_order(user_id)` 创建草稿订单**
2. **第二步调 `list_branches(user_id, user_latitude=?, user_longitude=?)` 列出分店**（如果用户提供位置）
3. 用户选了分店 → **调 `update_order_fields` 更新 branch_id**
4. 用户选完分店 → 调 `list_stylists(user_id, branch_id)` 列出发型师
5. 用户选了发型师 → **调 `update_order_fields` 更新 stylist_id**
6. 用户不知道选什么项目 → 调 `recommend_services(user_id, 用户需求)`
7. 用户选完项目 → 询问日期时间，电话，姓名，逐一调 `update_order_fields` 更新
8. 所有必填信息齐全 → **调 `confirm_order(user_id, order_id)`** 确认

## 规则
- 每步只调一个工具，等结果返回再继续
- 所有工具调用必须带 `user_id` 参数
- 用户可一口气说所有信息（如"明早10点去人民广场店找Tony剪发"），你解析后分步调工具
- 解析日期时间用 YYYY-MM-DD / HH:MM 格式
- 调 `update_order_fields` 增量更新，不要一次性传所有字段
- 工具返回错误时，把错误信息告诉用户让其重选
"""


async def build_booking_agent() -> Agent:
    """构建 Booking Agent (N7 修复: 改 async + 用 await registry.build_toolkit())。

    工具装载: 6 个 booking 工具，全部走 await toolkit.add_tool 官方 API。
    """
    booking_tool_names = {
        "create_draft_order", "update_order_fields", "confirm_order",
        "list_branches", "list_stylists", "recommend_services",
    }
    # 先按名字过滤要装的工具
    selected_tools = [t for t in registry.get_tools() if t.name in booking_tool_names]

    # 用官方 async add_tool 构造 toolkit
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
    logger.info(
        "Booking Agent 已构建: 工具=%d",
        len(selected_tools),
    )
    return agent


# 全局单例
_booking_agent_instance: Agent | None = None
_init_lock = asyncio.Lock()


async def get_booking_agent() -> Agent:
    """获取 Booking Agent 单例（异步懒加载 + 双检锁）。"""
    global _booking_agent_instance
    if _booking_agent_instance is None:
        async with _init_lock:
            if _booking_agent_instance is None:
                _booking_agent_instance = await build_booking_agent()
    return _booking_agent_instance


def reload_booking_agent() -> None:
    """热重载 Booking Agent。"""
    global _booking_agent_instance
    _booking_agent_instance = None
