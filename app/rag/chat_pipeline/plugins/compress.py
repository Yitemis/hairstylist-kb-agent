# -*- coding: utf-8 -*-
"""CompressPlugin: 上下文压缩 + Token 预算 (4 级优先级).

职责:
  1. 拿 reranked_hits -> 拼 context chunks (top context_top_n)
  2. 算 context_tokens (tiktoken 计数)
  3. 4 级 Token 预算分配:
     - high (30%): 固定区 (system + query)
     - mid (40%):  检索证据
     - low (20%):  长期记忆 + skill
     - spare (10%): 缓冲
  4. 超 mid 预算 -> 摘要/截断
  5. 进 reset zone (80%+) -> 主动建议 reset (日志)

输出:
  - ctx.context_chunks: [{content, source, score, citation_idx}, ...]
  - ctx.context_tokens: int
  - ctx.context_utilization: float
  - ctx.context_zone: smart/dumb/compress/reset
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


# 4 级 Token 预算 (high 30% / mid 40% / low 20% / spare 10%)
TOKEN_BUDGET = {
    "high": 0.30,
    "mid": 0.40,
    "low": 0.20,
    "spare": 0.10,
}
MID_PRIORITY_CAP = 0.40   # 检索证据占总 context 40%
LOW_PRIORITY_CAP = 0.20   # 记忆 + skill 占 20%


class CompressPlugin(Plugin):
    """上下文压缩 + Token 预算 Plugin.

    priority=70
    """

    name = "compress"
    priority = 70

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        from app.rag.context_monitor import (
            check_and_warn,
            count_tokens,
            ContextZone,
        )

        # 1. gate refuse 也要给个空 context (下游 Generate 会发固定回复)
        if ctx.gate_decision == "refuse" or not ctx.reranked_hits:
            ctx.context_chunks = []
            ctx.context_tokens = 0
            ctx.context_utilization = 0.0
            ctx.context_zone = ContextZone.SMART.value
            return ctx

        # 2. 拼 context chunks (top context_top_n)
        # 每个 chunk 限 4000 字符, 避免长 parent (7000+) 截到只剩标题
        chunks: list = []
        for i, h in enumerate(ctx.reranked_hits[:ctx.context_top_n], 1):
            content = (h.get("content") or "")[:4000]
            if not content:
                continue
            chunks.append({
                "citation_idx": i,
                "content": content,
                "source": h.get("filename", "unknown"),
                "document_id": h.get("document_id", ""),
                "score": h.get("rerank_score", h.get("score", 0.0)),
            })
        ctx.context_chunks = chunks

        # 3. 拼 context 文本 (LLM 用的格式)
        nl = "\n\n"
        ctx_text = nl.join(
            f"[{c['citation_idx']}] {c['content']}" for c in chunks
        ) or "(no results)"

        # 4. 算 token + zone
        usage = check_and_warn(ctx_text, model_name="default")
        ctx.context_tokens = usage.used_tokens
        ctx.context_utilization = usage.utilization
        ctx.context_zone = usage.zone.value

        # 5. zone = compress / reset -> 主动缩 context_top_n
        if usage.zone in (ContextZone.COMPRESS, ContextZone.RESET) and len(chunks) > 2:
            logger.warning(
                "Compress: zone=%s, truncating chunks %d -> 2",
                usage.zone.value, len(chunks),
            )
            chunks = chunks[:2]
            ctx.context_chunks = chunks
            ctx_text = nl.join(
                f"[{c['citation_idx']}] {c['content']}" for c in chunks
            ) or "(no results)"
            usage = check_and_warn(ctx_text, model_name="default")
            ctx.context_tokens = usage.used_tokens
            ctx.context_utilization = usage.utilization
            ctx.context_zone = usage.zone.value

        logger.info(
            "Compress: %d chunks %d tokens (%.1f%%) zone=%s",
            len(chunks), ctx.context_tokens,
            ctx.context_utilization * 100, ctx.context_zone,
        )
        return ctx


__all__ = ["CompressPlugin", "TOKEN_BUDGET"]
