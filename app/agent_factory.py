# -*- coding: utf-8 -*-
"""Agent 工厂：负责组装一个可用的 Agent 实例。

本模块把“模型 + 工具 + 系统提示词”拼装成一个 Agent。
M0 阶段先做最简版本（无工具、无 RAG），后续里程碑会逐步往里加东西。

【框架原理】
- Agent 是 AgentScope 的核心类，构造时至少需要 name / system_prompt / model 三样。
- 火山方舟提供 OpenAI 兼容接口，因此我们用框架自带的 OpenAIChatModel，
  只需把 base_url 指向火山方舟端点即可——这就是“模型可插拔”的体现。
"""
from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel

from .config import chat_config


# 美发知识助手的系统提示词（Agent 的“人设”与行为准则）
HAIRSTYLIST_SYSTEM_PROMPT = """你是一名资深的美发行业技术顾问，服务对象是发型师和门店员工。

你的职责：
- 用专业、准确、易懂的语言回答关于美发产品、染烫技术、服务话术与流程的问题。
- 当你不确定或知识库中没有相关信息时，如实说明，不要编造。
- 回答要简洁实用，必要时给出步骤或要点。

请始终以专业、友善的语气与用户交流。"""


def build_chat_model() -> OpenAIChatModel:
    """基于配置构建 Chat 模型（通过 OpenAI 兼容接口接入火山方舟）。

    Returns:
        OpenAIChatModel: 可直接传给 Agent 的模型实例。
    """
    credential = OpenAICredential(
        api_key=chat_config.api_key,
        base_url=chat_config.base_url,
    )
    return OpenAIChatModel(
        credential=credential,
        model=chat_config.model,
        # 火山方舟的 Doubao 等模型支持流式输出，打开它以便实现打字机效果
        stream=True,
    )


def build_agent() -> Agent:
    """组装并返回一个美发知识助手 Agent（M0 最简版）。

    Returns:
        Agent: 配置好模型与系统提示词的 Agent 实例。
    """
    return Agent(
        name="美发顾问",
        system_prompt=HAIRSTYLIST_SYSTEM_PROMPT,
        model=build_chat_model(),
    )
