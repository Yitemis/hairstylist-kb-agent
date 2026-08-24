# -*- coding: utf-8 -*-
"""IntakePlugin: 入口意图分类 + 路由决策.

负责:
  1. 分类 intent (knowledge / booking / casual / search)
  2. 安全预检 (业务边界)
  3. 路由决策: 选改写策略子集 + top_k + confidence threshold
  4. FAQ 不开 hyde, 冷门口语化才开 multiquery
"""
from __future__ import annotations

import logging
from typing import List

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


# 短问题/FAQ 特征: < 8 字符 + 含问号 -> 不开 hyde/subquery
def _looks_faq(message: str) -> bool:
    msg = (message or "").strip()
    if len(msg) < 8 and ("?" in msg or "？" in msg):
        return True
    # 高频 FAQ 关键词
    faq_kws = ("怎么用", "多少钱", "在哪", "营业时间", "电话", "地址")
    return any(kw in msg for kw in faq_kws)


# 模糊 query 特征: 包含口语化 / 不完整表达
def _looks_fuzzy(message: str) -> bool:
    msg = (message or "").strip()
    fuzzy_kws = ("那个", "就是", "那个啥", "懂吗", "怎么说", "啥意思")
    if any(kw in msg for kw in fuzzy_kws):
        return True
    # 没有主语 + 短
    if len(msg) < 10:
        return True
    return False


class IntakePlugin(Plugin):
    """入口分流 Plugin.

    priority=10 (Pipeline 第一个跑)
    """

    name = "intake"
    priority = 10

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        msg = (ctx.message or "").strip()
        if not msg:
            ctx.intent = "casual"
            ctx.intake_route = "casual"
            ctx.gate_decision = "refuse"
            ctx.gate_reason = "empty_message"
            return ctx

        # 1. 复用现有 classify_intent_llm (L1 dispatch 已用, 这里走同一路径)
        try:
            from app.services.chat_dispatcher import classify_intent_llm
            intent = await classify_intent_llm(msg, ctx.history)
        except Exception as e:
            logger.warning("Intake: classify_intent_llm failed, default knowledge: %s", e)
            intent = "knowledge"

        ctx.intent = intent

        # 2. 路由 + 改写策略选择
        if intent == "casual":
            # 闲聊不开 RAG
            ctx.intake_route = "casual"
            ctx.rewrite_strategies = []
        elif intent == "booking":
            # 预约不开 RAG (走 LangGraph 状态机)
            ctx.intake_route = "refuse"
            ctx.gate_decision = "refuse"
            ctx.gate_reason = "booking_intent_use_langgraph"
            ctx.rewrite_strategies = []
        else:
            # knowledge / search 走 RAG
            ctx.intake_route = "rag"
            if _looks_faq(msg):
                # FAQ: 用最少改写, top_k 也小
                ctx.rewrite_strategies = ["rewrite"]
                ctx.top_k = 3
            elif _looks_fuzzy(msg):
                # 模糊: 开 multiquery + rewrite
                ctx.rewrite_strategies = ["rewrite", "multiquery", "selfquery"]
                ctx.top_k = 5
            else:
                # 默认: 6 策略子集
                ctx.rewrite_strategies = [
                    "rewrite", "multiquery", "selfquery", "hyde",
                ]
                ctx.top_k = 5

        # 3. 同步到 plan 参数
        ctx.recall_top_k = max(30, ctx.top_k * 6)
        ctx.rerank_top_n = max(10, ctx.top_k * 2)
        ctx.context_top_n = ctx.top_k

        logger.info(
            "Intake: intent=%s route=%s strategies=%s top_k=%d",
            ctx.intent, ctx.intake_route, ctx.rewrite_strategies, ctx.top_k,
        )
        return ctx


__all__ = ["IntakePlugin"]
