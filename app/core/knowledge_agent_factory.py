# -*- coding: utf-8 -*-
"""知识问答专用 Agent (P0-2: 接入 RAGMiddleware 统一双轨制)。

N8 修复: build_knowledge_agent 改 async + 用 await registry.build_toolkit() 官方 API。
"""
from __future__ import annotations

import asyncio
import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model
from app.core.rag_middleware import get_rag_middleware
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_KNOWLEDGE_SYSTEM_PROMPT = """你是**美发专业知识顾问**，回答用户关于美发专业的问题。

## 你的能力
- 美发产品成分与作用（染膏、烫发水、护发素等）
- 染烫技术原理（染发化学、烫发物理化学等）
- 头皮护理、头发护理知识
- 美发工具使用
- 服务流程与操作规范

## 必须遵守
1. **每次回答前，必须先调用 `search_hair_knowledge(query=...)` 工具检索知识库**。
2. 严格基于检索结果回答，不要编造任何信息。
3. 如果检索结果为空或相关性低，**明确告诉用户"知识库暂无相关资料"**，不要硬编。
4. 回答要专业、简洁、易懂，必要时引用检索到的来源。
5. 每次回答包含一次检索调用即可，不要重复调用。

## 回答格式
- 先给出核心答案
- 必要时补充原理说明
- 引用来源文件（如有）
"""


async def build_knowledge_agent() -> Agent:
    """构建知识问答专用 Agent (P0-2 + N8 修复)。

    工具装载: search_hair_knowledge (用 await toolkit.add_tool 官方 API)。
    RAGMiddleware: 自动注入 RAG 上下文。
    """
    selected_tools = [t for t in registry.get_tools() if t.name == "search_hair_knowledge"]

    toolkit = Toolkit()
    for tool in selected_tools:
        await toolkit.add_tool(tool, group_name="basic")

    model = get_model("chat")
    rag_mw = get_rag_middleware()

    agent = Agent(
        name="美发知识顾问",
        system_prompt=_KNOWLEDGE_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )
    # 注入 RAGMiddleware
    if hasattr(agent, "middlewares"):
        agent.middlewares.append(rag_mw)
    else:
        if not hasattr(agent, "_middlewares"):
            agent._middlewares = []
        agent._middlewares.append(rag_mw)

    logger.info(
        "Knowledge Agent 已构建: 工具=%d, middleware=1",
        len(selected_tools),
    )
    return agent


# 全局单例 + 异步锁
_knowledge_agent_instance = None
_init_lock = asyncio.Lock()


async def get_knowledge_agent() -> Agent:
    """获取知识 Agent 单例（异步懒加载 + 双检锁）。"""
    global _knowledge_agent_instance
    if _knowledge_agent_instance is None:
        async with _init_lock:
            if _knowledge_agent_instance is None:
                _knowledge_agent_instance = await build_knowledge_agent()
    return _knowledge_agent_instance


def reload_knowledge_agent() -> None:
    """热重载 Knowledge Agent。"""
    global _knowledge_agent_instance
    _knowledge_agent_instance = None
