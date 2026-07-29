# -*- coding: utf-8 -*-
"""Agent 工厂：基于 AgentScope 原生能力构建业务专用 Agent。

100% 复用框架能力，不重造轮子：
- ReActAgent: 思考-行动循环
- TemporaryMemory: 对话记忆
- @tool 工具注册: 知识库检索
- ModelWrapper 后处理: 安全过滤拦截器
"""
from __future__ import annotations

import agentscope
from agentscope.agents import ReActAgent
from agentscope.memory import TemporaryMemory

from app.core.config import chat_config
from app.core.model_factory import get_model
from app.core.tool_registry import registry


_HAIR_SYSTEM_PROMPT = """你是一名资深的美发行业技术顾问，服务对象是发型师和门店员工。

【你的职责】
1. 用专业、准确、易懂的语言回答关于美发产品、染烫技术、服务流程与话术的问题；
2. 当问题涉及专业知识（如成分、配方、操作细节），请务必先调用 `search_hair_knowledge`
   工具检索知识库，再基于检索结果回答，不可编造；
3. 回答要结构清晰、实用，必要时分点说明或给出操作步骤；
4. 保持专业、友好、有耐心的语气。

【知识边界】
只回答美发相关的专业问题，不回答与美发无关的话题，
对于不确定的内容如实说明，不编造不存在的产品或技术。
"""


def build_agent(
    name: str = "美发顾问",
    system_prompt: str | None = None,
    enable_tools: bool = True,
) -> ReActAgent:
    """构建美发知识助手 Agent（基于 AgentScope ReActAgent）。

    Args:
        name: Agent 名称。
        system_prompt: 自定义系统提示词（默认使用美发领域专用）。
        enable_tools: 是否启用知识库检索工具。

    Returns:
        配置好的 ReActAgent 实例，支持工具调用 + 对话记忆。
    """
    # 1. 初始化 AgentScope（首次调用时执行，幂等）
    agentscope.init(
        project="hairstylist-kb-agent",
        save_log=False,  # 生产环境建议改为 True 并配置日志路径
    )

    # 2. 获取对话模型（从模型工厂，已带重试与安全拦截）
    model = get_model("chat")

    # 3. 构建 Agent
    agent = ReActAgent(
        name=name,
        system_prompt=system_prompt or _HAIR_SYSTEM_PROMPT,
        model=model,
        tools=registry.get_tools() if enable_tools else None,
        memory=TemporaryMemory(
            capacity=10,  # 保留最近 10 轮对话
        ),
    )

    return agent


# 全局单例（服务运行时共享）
_agent_instance: ReActAgent | None = None


def get_agent() -> ReActAgent:
    """获取全局 Agent 单例（懒加载，首次调用时初始化）。"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = build_agent()
    return _agent_instance


def reload_agent() -> None:
    """热重载 Agent（配置变更后调用，无需重启服务）。"""
    global _agent_instance
    _agent_instance = None
