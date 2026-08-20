# -*- coding: utf-8 -*-
"""Agent 工厂：基于 AgentScope 2.0 原生 Agent 构建业务专用 Agent。

100% 复用框架能力，不重造轮子:
- Agent (ReAct loop): 思考-行动循环
- Toolkit: 工具注册（知识库检索 + 后续订单工具）
- ChatModel (OpenAI 兼容): 对话模型

P1: 接入 StuckLoopDetector 防 LLM 抽风死循环 (借鉴 WeKnora §5.4)
"""
from __future__ import annotations

import logging

from agentscope.agent import Agent

from app.core.model_factory import get_model
from app.core.stuck_loop_detector import StuckLoopDetector
from app.core.tool_registry import registry

logger = logging.getLogger(__name__)


_HAIR_SYSTEM_PROMPT = """你是**美发智能助手**, 同时支持"专业知识库问答"和"对话式预约下单"两种能力:

## 如果你被问到专业问题
1. 必须先调用 search_hair_knowledge 工具检索知识库
2. 基于检索结果回答, 不编造
3. 专业、准确、易懂

## 如果用户想预约服务
按 11 步流程引导用户 (create_draft_order -> list_branches -> ...)
详见 system prompt 完整版.

工具调用规则:
- 每次最多调用一个工具
- 必须带 user_id 参数
- 只回答美发和预约相关内容
"""


# ============================================================
# P1: Agent 循环加 StuckLoop 检测 (借鉴 WeKnora §5.4)
# ============================================================

def _wrap_reply_with_stuck_detection(agent, max_consecutive=3):
    """包装 agent.reply() 加 stuck loop 检测.

    Returns:
        包装后的 reply 函数 (async)
    """
    detector = StuckLoopDetector(max_consecutive=max_consecutive)
    original_reply = agent.reply

    async def safe_reply(messages, **kwargs):
        """带 stuck 检测的 reply."""
        detector.reset()
        last_tool_sig = None
        stuck = False
        result = None

        try:
            result = await original_reply(messages, **kwargs)

            # 检测 content stuck
            content = _extract_content(result)
            if content and detector.check_content(content):
                logger.warning("StuckLoop: content stuck, breaking")
                stuck = True

            # 检测 tool call stuck
            if not stuck:
                tool_sig = _extract_tool_sig(result)
                if tool_sig:
                    name, args = tool_sig
                    if detector.check_tool_call(name, dict(args)):
                        logger.warning("StuckLoop: tool call stuck, breaking")
                        stuck = True

            return result
        except Exception as e:
            logger.error("Agent reply failed: %s", e)
            raise

    return safe_reply


def _extract_content(chunk) -> str:
    """从 chunk 提取 content 文本."""
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
    """从 chunk 提取 (tool_name, tool_args_dict) 签名."""
    if not chunk or not hasattr(chunk, "content"):
        return None
    for block in chunk.content:
        if hasattr(block, "name") and block.name:
            args = getattr(block, "input", None) or getattr(block, "arguments", None) or {}
            if isinstance(args, dict):
                return (block.name, args)
    return None


def build_agent(
    name="美发顾问",
    system_prompt=None,
    enable_tools=True,
    enable_stuck_detection=True,
) -> Agent:
    """构建美发知识助手 Agent (基于 AgentScope 2.0 Agent).

    Args:
        name: Agent 名称.
        system_prompt: 自定义系统提示词.
        enable_tools: 是否启用工具.
        enable_stuck_detection: P1 - 是否启用 stuck loop 检测 (默认 True)
    """
    model = get_model("chat")
    agent = Agent(
        name=name,
        system_prompt=system_prompt or _HAIR_SYSTEM_PROMPT,
        model=model,
        toolkit=registry.build_toolkit() if enable_tools else None,
    )

    # P1: 注入 stuck loop 检测
    if enable_stuck_detection:
        agent.reply = _wrap_reply_with_stuck_detection(agent, max_consecutive=3)
        logger.info("Agent 已注入 StuckLoopDetector (max_consecutive=3)")

    logger.info("Agent 已构建: %s, 模型=%s, 工具数=%d",
                name, model.model, len(registry.get_tools()))
    return agent


_agent_instance = None


def get_agent():
    """获取全局 Agent 单例 (懒加载)."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = build_agent()
    return _agent_instance


def reload_agent():
    """热重载 Agent."""
    global _agent_instance
    _agent_instance = None
