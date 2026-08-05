"""带缓存的 LLM 调用（避免重复扣费）。"""
from __future__ import annotations

import logging
from typing import Any, List

from app.core.cache.llm_cache import get_llm_cache, hash_messages

logger = logging.getLogger(__name__)


async def chat_with_cache(
    model,
    messages: list[dict],
    use_cache: bool = True,
) -> Any:
    """调 LLM（带缓存）。

    Args:
        model: ChatModelBase 实例
        messages: OpenAI 格式 messages
        use_cache: 是否启用缓存（流式应该设为 False）

    Returns: LLM 响应
    """
    from app.core.metrics import llm_cache_total
    cache = get_llm_cache()
    cache_key = hash_messages(messages, model=getattr(model, "model", ""))

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            llm_cache_total.labels(result="hit").inc()
            logger.info("LLM cache hit (key=%s...)", cache_key[:8])
            return cached

    llm_cache_total.labels(result="miss").inc()
    from agentscope.message import TextBlock, UserMsg
    as_msgs = []
    for m in messages:
        if m["role"] == "system":
            as_msgs.append(UserMsg(name="system", content=[TextBlock(text=m["content"])]))
        elif m["role"] == "user":
            text = m.get("content", "")
            if isinstance(text, str):
                as_msgs.append(UserMsg(name="user", content=[TextBlock(text=text)]))
    resp = await model(as_msgs, stream=False)

    # 缓存响应
    if use_cache:
        cache.set(cache_key, resp)
        logger.info("LLM cache set (key=%s...)", cache_key[:8])
    return resp
