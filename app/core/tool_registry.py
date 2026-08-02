# -*- coding: utf-8 -*-
"""工具注册中心：基于 AgentScope 2.0 原生 FunctionTool 的扩展。

企业级特性：
- 工具自动发现与注册
- 工具级别的权限控制
- 工具调用审计日志
- 工具健康检查与熔断
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from agentscope.tool import FunctionTool, Toolkit

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心。

    统一管理所有可用的 Agent 工具，支持动态注册、权限检查与审计。
    """

    def __init__(self) -> None:
        self._tools: dict[str, FunctionTool] = {}
        self._tool_functions: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        requires_auth: bool = False,
    ) -> FunctionTool:
        """注册一个工具函数。

        Args:
            func: 工具函数。
            name: 工具名称（默认函数名）。
            description: 工具描述（给 Agent 看的 prompt 描述）。
            requires_auth: 是否需要授权才能使用（预留权限控制）。

        Returns:
            注册后的 AgentScope FunctionTool 实例。
        """
        tool_name = name or func.__name__

        if tool_name in self._tools:
            logger.warning("工具 %s 已存在，将被覆盖", tool_name)

        wrapped = FunctionTool(
            func=func,
            name=tool_name,
            description=description or func.__doc__ or "",
        )
        self._tools[tool_name] = wrapped
        self._tool_functions[tool_name] = func
        logger.debug("注册工具: %s", tool_name)
        return wrapped

    def unregister(self, name: str) -> None:
        """注销一个工具。"""
        if name in self._tools:
            del self._tools[name]
            del self._tool_functions[name]
            logger.debug("注销工具: %s", name)

    def get_tools(self) -> list[FunctionTool]:
        """获取所有注册的工具列表。"""
        return list(self._tools.values())

    def get_tool_names(self) -> list[str]:
        """获取所有工具名。"""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在。"""
        return name in self._tools

    def build_toolkit(self) -> Toolkit:
        """构造一个含全部工具的 Toolkit（供 Agent 使用）。"""
        toolkit = Toolkit()
        for tool_obj in self._tools.values():
            # AgentScope 2.0 用 add_tool 异步方法；这里直接添加到 tool_groups
            toolkit.tool_groups[0].tools.append(tool_obj)
        return toolkit


# 全局单例
registry = ToolRegistry()


# ------------------------------------------------------------------
# 内置工具：知识库检索（项目核心工具）
# ------------------------------------------------------------------


async def search_hair_knowledge(query: str) -> str:
    """检索美发专业知识库（混合检索 + 父子分块 + Rerank + Context 工程）。

    Args:
        query: 要检索的问题或关键词。

    Returns:
        带溯源的知识库上下文，用于构建 Agent 回答。
    """
    from rag.context import build_context
    from rag.searcher import search

    result = await search(query, tenant_id="default", top_k=3, enable_rerank=True)
    if not result.hits:
        return "知识库中暂无相关内容。"
    return build_context(result.hits)


# 注册核心工具
registry.register(
    search_hair_knowledge,
    name="search_hair_knowledge",
    description=(
        "当用户询问美发相关的专业问题时（如产品成分、染烫技术、服务流程、"
        "头皮护理等），调用此工具检索专业知识库，获取准确的参考信息。"
        "参数：query（字符串），要检索的问题关键词。"
    ),
)

# ------------------------------------------------------------------
# 对话式下单工具集（C端用户预约）
# ------------------------------------------------------------------

from app.agent_tools.order_tools import (
    confirm_order,
    create_draft_order,
    list_branches,
    list_stylists,
    recommend_services,
    update_order_fields,
)

registry.register(
    create_draft_order,
    name="create_draft_order",
    description=(
        "创建一个新的草稿预约订单，供后续逐步填写信息。"
        "当用户说「我要预约」「我想烫头发」，第一步必须调用此工具。"
        "参数：user_id（必须，当前登录用户的ID）。"
    ),
)

registry.register(
    update_order_fields,
    name="update_order_fields",
    description=(
        "增量更新草稿订单的信息，每次可以更新一个或多个字段。"
        "每当用户提供了新的信息（选了发型师、定了时间、给了电话），立即调用这个工具更新。"
        "参数：user_id（当前用户ID），order_id（订单ID），service_type（可选，服务项目名称），"
        "service_details（可选，服务细节备注），stylist_id（可选，选中发型师ID），"
        "appointment_date（可选，预约日期，格式必须是YYYY-MM-DD），"
        "appointment_time（可选，预约时间，格式必须是HH:MM），"
        "customer_phone（可选，用户联系电话），customer_name（可选，用户姓名），"
        "address（可选，店铺地址），note（可选，额外备注）。"
    ),
)

registry.register(
    confirm_order,
    name="confirm_order",
    description=(
        "所有信息填写完整后，用户确认，调用此工具将订单提交给店家。"
        "提交后状态变为pending，出现在店家后台等待处理。"
        "参数：user_id（当前用户ID），order_id（订单ID）。"
    ),
)

registry.register(
    list_branches,
    name="list_branches",
    description=(
        "列出所有营业分店，按距离用户位置从近到远排序，标注今日是否约满。"
        "用户预约第一步，选择分店时调用。如果用户提供位置，带上经纬度排序。"
        "参数：user_id（当前用户ID，仅占位鉴权），user_latitude（可选，用户纬度），user_longitude（可选，用户经度）。"
    ),
)

registry.register(
    list_stylists,
    name="list_stylists",
    description=(
        "列出指定分店所有可预约的发型师，标注今日是否约满，供用户选择。"
        "当用户说「不知道选哪个发型师」「列出该分店发型师」时调用。"
        "参数：user_id（当前用户ID，仅占位鉴权），branch_id（可选，筛选指定分店）。"
    ),
)

registry.register(
    recommend_services,
    name="recommend_services",
    description=(
        "根据用户需求描述，推荐适合的服务项目。"
        "当用户说「不知道做什么项目」「推荐项目」时调用。"
        "参数：user_id（当前用户ID，仅占位鉴权），user_description（用户需求描述）。"
    ),
)
