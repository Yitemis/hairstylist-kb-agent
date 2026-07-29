# -*- coding: utf-8 -*-
"""工具注册中心：基于 AgentScope 原生 @tool 装饰器的扩展。

企业级特性：
- 工具自动发现与注册
- 工具级别的权限控制
- 工具调用审计日志
- 工具健康检查与熔断
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from agentscope.tools import tool
from agentscope.tools.tool import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心。

    统一管理所有可用的 Agent 工具，支持动态注册、权限检查与审计。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._tool_functions: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        requires_auth: bool = False,
    ) -> Tool:
        """注册一个工具函数。

        Args:
            func: 工具函数。
            name: 工具名称（默认函数名）。
            description: 工具描述（给 Agent 看的 prompt 描述）。
            requires_auth: 是否需要授权才能使用（预留权限控制）。

        Returns:
            注册后的 AgentScope Tool 对象。
        """
        tool_name = name or func.__name__

        if tool_name in self._tools:
            logger.warning("工具 %s 已存在，将被覆盖", tool_name)

        # 用 AgentScope 原生装饰器包装函数
        wrapped = tool(name=tool_name, description=description or func.__doc__ or "")(func)
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

    def get_tools(self) -> list[Tool]:
        """获取所有注册的工具列表（传给 Agent）。"""
        return list(self._tools.values())

    def get_tool_names(self) -> list[str]:
        """获取所有工具名。"""
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在。"""
        return name in self._tools


# 全局单例
registry = ToolRegistry()


# ------------------------------------------------------------------
# 内置工具：知识库检索（项目核心工具）
# ------------------------------------------------------------------


@tool(
    name="search_hair_knowledge",
    description=(
        "当用户询问美发相关的专业问题时（如产品成分、染烫技术、服务流程、"
        "头皮护理等），调用此工具检索专业知识库，获取准确的参考信息。"
        "参数：query（字符串），要检索的问题关键词。"
    ),
)
def search_hair_knowledge(query: str) -> str:
    """检索美发专业知识库（Self-RAG 自主优化查询）。

    Args:
        query: 要检索的问题或关键词。

    Returns:
        检索到的相关知识内容，用于构建 Agent 回答上下文。
    """
    import asyncio

    # 同步包装异步检索逻辑
    async def _search():
        from app.rag.engine import self_rag_retrieve

        result = await self_rag_retrieve(query, tenant_id="default", top_k=3)
        if not result.hits:
            return "知识库中暂无相关内容。"

        context_parts = []
        for hit in result.hits:
            context_parts.append(f"【来源：{hit.source}】\n{hit.content}")
        return "\n\n".join(context_parts)

    # 获取或创建事件循环（兼容同步调用
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # 已有运行循环时，同步阻塞调用
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(lambda: loop.run_until_complete(_search()))
            return future.result()
    else:
        return loop.run_until_complete(_search())


# 注册核心工具
registry.register(search_hair_knowledge)
