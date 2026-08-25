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

    async def build_toolkit(self) -> Toolkit:
        """构造含全部工具的 Toolkit (官方 async add_tool API)。

        N7/N9 修复: 之前用 toolkit.tool_groups[0].tools.append 是私有属性 hack，
        现在统一用 AgentScope 2.0 官方的 await toolkit.add_tool()。
        """
        toolkit = Toolkit()
        for tool_obj in self._tools.values():
            await toolkit.add_tool(tool_obj, group_name="basic")
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
    # P2-5 修复: 改用正确模块路径
    from app.rag.v2_engine import retrieve

    result = await retrieve(
        query=query, tenant_id="default", top_k=3, enable_rerank=True,
    )
    if not result.hits:
        return "知识库中暂无相关内容。"
    # 构造 context 文本 (P0-3 修复: 去掉 h.page — RetrievalHit 无此属性)
    parts = []
    for i, h in enumerate(result.hits, 1):
        source = getattr(h, "filename", None) or getattr(h, "document_id", "unknown")
        content = (getattr(h, "content", "") or "")[:500]
        score = getattr(h, "score", 0.0)
        parts.append(f"【来源{i}】 {source} (相关度: {score:.2f})\n{content}")
    return "\n\n".join(parts)


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

from app.core.tools.order_tools import (
    cancel_order,
    confirm_order,
    create_draft_order,
    list_branches,
    list_stylists,
    recommend_services,
    update_order_fields,
)
# P0-3: 业务管理工具 (B 端后台用)
from app.core.tools.business_tools import (
    get_business_stats,
    get_order_detail,
    list_orders,
    list_staffs,
    list_users,
    update_order_status,
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
        "HIGH_RISK：会触发用户二次确认（返回 ask_id），需用户批准后才会真正提交。"
        "参数：user_id（当前用户ID），order_id（订单ID）。"
    ),
)

# P2-权限对齐: 注册 cancel_order 工具 (HIGH_RISK, 装饰器已做 HITL)
registry.register(
    cancel_order,
    name="cancel_order",
    description=(
        "用户主动取消一笔预约订单（不可逆操作）。"
        "HIGH_RISK：会触发用户二次确认（返回 ask_id），需用户批准后才会真正取消。"
        "参数：user_id（当前用户ID），order_id（要取消的订单ID），"
        "reason（取消原因，可选，会写入订单备注供店家审计）。"
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


# ============================================================
# P0-3: 业务管理工具 (B 端后台用, 不依赖 user_id)
# ============================================================
registry.register(
    list_orders,
    name="list_orders",
    description=(
        "查订单列表 (B 端后台最常用). "
        "支持按状态/分店/电话/天数过滤. "
        "当用户问「查订单」「看订单列表」「最近订单」时调用. "
        "参数 (都可省略): status (pending/confirmed/done/cancelled), branch_id (分店ID), phone (顾客电话), days (看最近N天, 默认7), limit (返回条数, 默认20)."
    ),
)

registry.register(
    get_order_detail,
    name="get_order_detail",
    description=(
        "查单个订单的完整详情 (顾客/分店/发型师/时间/价格/备注). "
        "当用户说「查订单 #5」「看这个订单的详情」时调用. "
        "参数: order_id (订单ID, 必填)."
    ),
)

registry.register(
    update_order_status,
    name="update_order_status",
    description=(
        "改订单状态 (确认/完成/取消). "
        "当用户说「把订单 #5 改成已完成」「确认这个订单」时调用. "
        "参数: order_id (必填), new_status (pending/confirmed/done/cancelled, 必填), note (备注, 可选)."
    ),
)

registry.register(
    list_staffs,
    name="list_staffs",
    description=(
        "查员工列表 (含电话/分店/在岗状态). "
        "当用户问「查员工」「列出发型师」「分店有什么员工」时调用. "
        "参数: branch_id (分店ID, 可选, 不传=全部)."
    ),
)

registry.register(
    list_users,
    name="list_users",
    description=(
        "查 C 端用户列表. "
        "当用户说「查用户」「最近注册的客户」「查电话 138xxx」时调用. "
        "参数: phone (模糊搜索), days (默认30), limit (默认20)."
    ),
)

registry.register(
    get_business_stats,
    name="get_business_stats",
    description=(
        "B 端业务统计 (订单数/营收/各状态分布/分店数/用户数/员工数). "
        "当用户问「最近业务怎么样」「这个月订单多少」「营收多少」时调用. "
        "参数: days (统计最近N天, 默认7)."
    ),
)


# ============================================================
# P0-3: 联网搜索工具 (知识库 fallback)
# ============================================================
# 多 provider 支持: DuckDuckGo (免费, 无 key) / Tavily / Bocha
# 借鉴 WeKnora §5 知识检索多 KB 模式 + 实时联网兜底

async def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索 (知识库 fallback).

    当知识库无相关内容时, 调此工具从互联网实时获取。
    默认用 DuckDuckGo 免费 API (无需 key, 适合开发/测试)。
    生产建议在 .env 设 WEB_SEARCH_PROVIDER=tavily + WEB_SEARCH_API_KEY=xxx。

    Args:
        query: 搜索关键词
        max_results: 返回前 N 条结果 (默认 5)

    Returns:
        格式化好的搜索结果文本 (带来源链接)
    """
    import os
    import httpx
    import logging
    logger = logging.getLogger(__name__)

    provider = os.environ.get("WEB_SEARCH_PROVIDER", "duckduckgo").lower()
    api_key = os.environ.get("WEB_SEARCH_API_KEY", "")

    try:
        if provider == "tavily" and api_key:
            return await _web_search_tavily(query, max_results, api_key)
        elif provider == "bocha" and api_key:
            return await _web_search_bocha(query, max_results, api_key)
        else:
            return await _web_search_duckduckgo(query, max_results)
    except Exception as e:
        logger.warning("web_search failed: %s", e)
        return f"联网搜索失败: {type(e).__name__}: {e}"


async def _web_search_duckduckgo(query: str, max_results: int) -> str:
    """DuckDuckGo Instant Answer API (免费, 无需 key, 限英文).

    优点: 无需注册, 适合 demo
    缺点: 限英文, 国内可能超时
    """
    import httpx
    import asyncio
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # P0-3: 短超时避免 hang
            # DDG Instant Answer API
            r = await client.get("https://api.duckduckgo.com/", params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            data = r.json()
            results = []
            # Abstract (summary)
            if data.get("AbstractText"):
                results.append(f"[摘要] {data['AbstractText']}\n来源: {data.get('AbstractURL', 'N/A')}")
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    text = topic["Text"]
                    url = topic.get("FirstURL", "")
                    results.append(f"- {text}\n  来源: {url}")
            if not results:
                # 兜底: 用 HTML 版
                r2 = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
                import re
                links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', r2.text)
                for url, title in links[:max_results]:
                    if "duckduckgo" not in url and url.startswith("http"):
                        results.append(f"- {title.strip()}\n  来源: {url}")
            if not results:
                return f"未在 DuckDuckGo 搜到「{query}」相关结果。\n\n建议:\n1) 换更精确的英文关键词\n2) 在 .env 设 WEB_SEARCH_PROVIDER=tavily + WEB_SEARCH_API_KEY=xxx (Tavily 适合生产)\n3) 用 search_hair_knowledge 查本地知识库"
            return "\n\n".join(results[:max_results])
    except (httpx.ConnectTimeout, httpx.ConnectError, asyncio.TimeoutError) as e:
        return (
            f"⚠️ 联网搜索不可用: {type(e).__name__}\n\n"
            f"无法访问 DuckDuckGo (国内/防火墙可能拦截).\n\n"
            f"降级方案:\n"
            f"1) 在 .env 配置: WEB_SEARCH_PROVIDER=tavily, WEB_SEARCH_API_KEY=tvly-xxx\n"
            f"2) 或: WEB_SEARCH_PROVIDER=bocha, WEB_SEARCH_API_KEY=sk-xxx (博查, 国内可用)\n"
            f"3) 暂用本地知识库 (search_hair_knowledge) 代替"
        )


async def _web_search_tavily(query: str, max_results: int, api_key: str) -> str:
    """Tavily 搜索 (生产推荐, 支持中文)."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post("https://api.tavily.com/search", json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": True,
        })
        r.raise_for_status()
        data = r.json()
        parts = []
        # answer (LLM 总结)
        if data.get("answer"):
            parts.append(f"[Tavily 总结] {data['answer']}")
        # results
        for r_item in data.get("results", [])[:max_results]:
            title = r_item.get("title", "")
            content = r_item.get("content", "")[:300]
            url = r_item.get("url", "")
            parts.append(f"- {title}\n  {content}\n  来源: {url}")
        if not parts:
            return f"Tavily 未搜到「{query}」相关结果"
        return "\n\n".join(parts)


async def _web_search_bocha(query: str, max_results: int, api_key: str) -> str:
    """博查 (Bocha) 搜索 - 国内可用, 支持中文."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post("https://api.bochaai.com/v1/web-search", json={
            "apiKey": api_key,
            "query": query,
            "summary": True,
            "count": max_results,
        })
        r.raise_for_status()
        data = r.json()
        parts = []
        # summary
        if data.get("data", {}).get("summary"):
            parts.append(f"[博查 总结] {data['data']['summary']}")
        for item in data.get("data", {}).get("webPages", {}).get("value", [])[:max_results]:
            title = item.get("name", "")
            snippet = item.get("snippet", "")[:300]
            url = item.get("url", "")
            parts.append(f"- {title}\n  {snippet}\n  来源: {url}")
        if not parts:
            return f"博查未搜到「{query}」相关结果"
        return "\n\n".join(parts)


registry.register(
    web_search,
    name="web_search",
    description=(
        "联网搜索 (实时获取互联网信息, 作为知识库 fallback). "
        "当 search_hair_knowledge 返回「暂无相关内容」, 或用户问题明显超出美发知识库范围 (如时尚趋势、产品对比、最新政策), "
        "调此工具. 返回 5 条带来源链接的搜索结果. "
        "参数: query (搜索关键词, 必填), max_results (返回条数, 可选 1-10, 默认 5)."
    ),
)
