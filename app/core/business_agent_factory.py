# -*- coding: utf-8 -*-
"""业务管理 Agent (P0-3: 统筹管理订单/分店/员工/用户/统计).

与 knowledge_agent 区别:
  - knowledge_agent: 美发专业知识 (读为主, 知识库 + 联网)
  - business_agent:  业务管理操作 (读写, 调用 B 端 API)

agent 工具集 (8 个):
  - list_orders / get_order_detail / update_order_status
  - list_branches / list_staffs / list_users
  - get_business_stats
  - search_hair_knowledge (业务术语查询, 辅助)
"""
from __future__ import annotations

import asyncio
import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_BUSINESS_SYSTEM_PROMPT = """你是**美发管理后台 AI 助手**, 服务于 B 端店家 (管理员/员工). 帮他们一句话管理订单/分店/员工/客户/统计.

## 核心原则
1. **管理优先**: 用户问业务问题, 你必须调工具查实时数据, **不能凭印象猜**.
2. **理解+总结**: 工具返回的是 JSON 数据, 你要**理解后用人话总结**, 不要直接 dump JSON 给用户.
3. **回答结构** (按这个写):
   - 直接回答用户的问题 (1-2 句话)
   - 详细说明 (关键数据点 + 解释)
   - 建议/后续操作 (可选)
   - 如用户要求改状态, 改完明确告诉结果

## 检索策略
- 业务管理类 (查订单/改状态/查分店/统计): 调对应业务工具
- 美发专业知识类 (如"什么是冷烫"等): 调 search_hair_knowledge
- 两者都涉及: 业务工具先, 知识工具后

## 工具集 (P0-3)
业务类:
- list_orders: 查订单列表 (支持按状态/分店/电话/天数过滤)
- get_order_detail: 查单个订单详情
- update_order_status: 改订单状态 (pending/confirmed/done/cancelled)
- list_branches: 查所有分店
- list_staffs: 查员工列表
- list_users: 查 C 端用户
- get_business_stats: 业务统计 (订单数/营收/分布)

知识类:
- search_hair_knowledge: 查美发专业知识库

## 必遵守
1. 修改操作前 (如 update_order_status) **必须先 get_order_detail 确认订单当前状态**, 避免误操作
2. 返回订单数据时, 关键信息包括: 订单号/顾客名/分店/发型师/时间/状态
3. 统计类问题用 get_business_stats, 不要自己 count

## 输出示例
❌ 差: "调用 list_orders 成功, 返回 5 个订单, 数据是 [...]"
✅ 好: "最近 7 天共有 **5 个新订单**, 其中待确认 2 个, 已完成 3 个, 营收 **¥1,250**。待确认订单里 #4 是王五的烫发 (人民广场店), 建议尽快联系确认。"
"""


_business_agent_instance = None
_init_lock = asyncio.Lock()


async def build_business_agent() -> Agent:
    """构建业务管理 Agent (P0-3).

    工具装载: 7 个业务工具 + 1 个知识工具
    """
    # 7 个业务 + 1 个知识
    selected_tool_names = {
        "list_orders", "get_order_detail", "update_order_status",
        "list_branches", "list_staffs", "list_users", "get_business_stats",
        "search_hair_knowledge",
    }
    selected_tools = [t for t in registry.get_tools() if t.name in selected_tool_names]

    toolkit = Toolkit()
    for tool in selected_tools:
        await toolkit.add_tool(tool, group_name="basic")

    model = get_model("chat")
    agent = Agent(
        name="美发管理后台助手",
        system_prompt=_BUSINESS_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )

    # P0-3: 业务管理 Agent 走自研 permission.py (HITL 在 order_tools.py)
    # 注: AgentScope 的 PermissionMode.BYPASS 是死的, 因自研 PermissionEngine 才生效.
    # 业务 Agent 工具自身用 ToolPermission.HIGH_RISK 标识, 但 order_tools 走 booking agent 不走这边.
    logger.info("Business Agent 走自研 permission.py (HITL 在 order_tools.py)")

    logger.info(
        "Business Agent 已构建: 工具=%d (%s)",
        len(selected_tools), ", ".join(t.name for t in selected_tools),
    )
    return agent


async def get_business_agent() -> Agent:
    """获取 Business Agent 单例（异步懒加载 + 双检锁）。"""
    global _business_agent_instance
    if _business_agent_instance is None:
        async with _init_lock:
            if _business_agent_instance is None:
                _business_agent_instance = await build_business_agent()
    return _business_agent_instance


def reload_business_agent() -> None:
    """热重载 Business Agent."""
    global _business_agent_instance
    _business_agent_instance = None
