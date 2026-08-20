# -*- coding: utf-8 -*-
"""Long-Term Memory Middleware: 自动注入 + 自动提取.

P1-2: 借鉴 JavaGuide section 3.6 (记忆 6 阶段模型).

自动注入 (onReasoning):
  1. 从 DB 拿用户事实
  2. 渲染成可注入段
  3. 加到 system_prompt

自动提取 (onReply 后):
  1. 从 user + ai 提取事实 (LLM)
  2. 保存到 user_profiles
  3. 下次自动注入
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


# 自动注入 (incoming)

async def load_user_facts(user_id: int) -> list:
    try:
        from app.core.long_term_memory import get_user_facts
        return await get_user_facts(user_id)
    except Exception as e:
        logger.warning("load_user_facts failed: %s", e)
        return []


def build_facts_injection(facts: list) -> str:
    if not facts:
        return ""
    from app.core.long_term_memory import build_facts_injection as _b
    return _b(facts)


async def inject_user_facts(user_id: int, system_prompt: str, max_facts: int = 20) -> str:
    facts = await load_user_facts(user_id)
    if not facts:
        return system_prompt
    facts = facts[:max_facts]
    injection = build_facts_injection(facts)
    if not injection:
        return system_prompt
    sep = chr(10) + chr(10)  # 2 newlines
    return injection + sep + system_prompt


# 自动提取 (outgoing)

async def extract_and_save_after_chat(user_id: int, user_message: str, ai_message: str) -> int:
    try:
        from app.core.long_term_memory import extract_and_save_facts
        return await extract_and_save_facts(user_id, user_message, ai_message)
    except Exception as e:
        logger.warning("extract_and_save_after_chat failed: %s", e)
        return 0


# Middleware 类

class LongTermMemoryMiddleware:
    """长期记忆 middleware (借鉴 JavaGuide section 3.6 + AgentScope 2.0)."""

    def __init__(self, max_facts: int = 20, auto_extract: bool = True):
        self.max_facts = max_facts
        self.auto_extract = auto_extract

    async def on_reasoning(self, ctx, next_fn, message: str = "") -> Any:
        user_id = getattr(ctx, "user_id", None)
        if user_id is None:
            return await next_fn()

        if hasattr(ctx, "system_prompt") and ctx.system_prompt:
            original = ctx.system_prompt
            ctx.system_prompt = await inject_user_facts(
                user_id, original, max_facts=self.max_facts,
            )

        return await next_fn()

    async def on_reply(self, ctx, next_fn) -> Any:
        result = await next_fn()

        if not self.auto_extract:
            return result

        user_id = getattr(ctx, "user_id", None)
        user_message = getattr(ctx, "last_user_message", "")
        ai_message = getattr(ctx, "last_ai_message", "")

        if user_id and user_message and ai_message:
            import asyncio
            asyncio.create_task(
                extract_and_save_after_chat(user_id, user_message, ai_message)
            )

        return result


__all__ = [
    "LongTermMemoryMiddleware",
    "build_facts_injection",
    "extract_and_save_after_chat",
    "inject_user_facts",
    "load_user_facts",
]
