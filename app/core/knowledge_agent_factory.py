# -*- coding: utf-8 -*-
"""知识问答专用 Agent：只装载 RAG 工具，让 LLM 自主决定检索。

这是把"知识库问答"业务从 chat 端点剥离出来的关键模块。

为什么需要独立的 Agent？
- Booking 流程是确定的：分店 → 发型师 → 服务 → 时间 → 确认
  这种"已知流程"用业务调度（_handle_booking_flow）更可靠
- Knowledge 流程是不确定的：用户问啥都难预知
  这种"探索性查询"用 ReAct Agent 让 LLM 自主决定调哪个工具更灵活

设计原则（参考 AgentScope 2.0）：
- 只装载 search_hair_knowledge 一个工具，避免 Agent 误调 booking 工具
- 系统提示词强调"必须先检索，不能编造"
- 出错兜底：Agent 失败时降级到纯 LLM
"""
from __future__ import annotations

import logging

from agentscope.agent import Agent
from agentscope.tool import Toolkit

from app.core.model_factory import get_model

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


def build_knowledge_agent() -> Agent:
    """构建知识问答专用 Agent。

    Returns:
        Agent: 配置好的 ReAct Agent，工具集只含 search_hair_knowledge。
    """
    from app.core.tool_registry import registry

    # 只装载 RAG 工具，避免 Agent 误调 booking 工具
    toolkit = Toolkit()
    for tool in registry.get_tools():
        if tool.name == "search_hair_knowledge":
            toolkit.tool_groups[0].tools.append(tool)
            break

    model = get_model("chat")
    agent = Agent(
        name="美发知识顾问",
        system_prompt=_KNOWLEDGE_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )
    logger.info("Knowledge Agent 已构建: 工具数=%d", len(toolkit.tool_groups[0].tools))
    return agent


# 全局单例
_knowledge_agent_instance: Agent | None = None


def get_knowledge_agent() -> Agent:
    """获取全局知识 Agent 单例（懒加载）。"""
    global _knowledge_agent_instance
    if _knowledge_agent_instance is None:
        _knowledge_agent_instance = build_knowledge_agent()
    return _knowledge_agent_instance


def reload_knowledge_agent() -> None:
    """热重载 Knowledge Agent（配置变更后调用）。"""
    global _knowledge_agent_instance
    _knowledge_agent_instance = None
