# -*- coding: utf-8 -*-
"""QueryRewritePlugin: 6 策略并行改写 (按 Intake 选子集).

策略 (默认 6):
  1. rewrite        LLM 改写 (口语化 -> 专业)
  2. subquery       复杂问题拆解
  3. hyde           假设文档嵌入
  4. stepback       后退一步
  5. multiquery     多角度
  6. selfquery      提取 metadata filter

输出:
  - ctx.candidate_queries: 去重后的候选 query 列表
  - ctx.rewrite_candidates_meta: 每条 (strategy, original, candidate)
"""
from __future__ import annotations

import logging
from typing import List

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class QueryRewritePlugin(Plugin):
    """Query 改写 Plugin (Phase 2).

    priority=20
    """

    name = "query_rewrite"
    priority = 20

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        # 没选策略 (casual / refuse) 直接跳过
        if not ctx.rewrite_strategies:
            ctx.candidate_queries = [ctx.message]
            return ctx

        # 已经有候选 (被 gate 拒绝后 retry), 复用
        if ctx.candidate_queries:
            return ctx

        # 非中文 query 不调 LLM 改写 (改写可能把英翻中, 跟英文 KB 不匹配)
        def _detect_lang(text):
            cn = sum(1 for c in text if "一" <= c <= "鿿")
            en = sum(1 for c in text if c.isascii() and c.isalpha())
            if cn > en:
                return "zh"
            if en > cn * 2:
                return "en"
            return "mixed"

        lang = _detect_lang(ctx.message)
        if lang != "zh":
            logger.info(
                "QueryRewrite: lang=%s, skip LLM rewrite, use original",
                lang,
            )
            ctx.candidate_queries = [ctx.message]
            return ctx

        try:
            from app.rag.query.rewriter import rewrite_query
            results = await rewrite_query(
                ctx.message, strategies=ctx.rewrite_strategies,
            )
        except Exception as e:
            logger.warning("Query rewrite failed: %s, use original", e)
            ctx.candidate_queries = [ctx.message]
            return ctx

        # 收集候选 + 元信息
        meta: List[dict] = []
        seen: set = set()
        candidates: List[str] = [ctx.message]  # 原 query 必带
        seen.add(ctx.message.strip())

        for r in results:
            for c in r.candidates:
                c_clean = (c or "").strip()
                if not c_clean or c_clean in seen:
                    continue
                candidates.append(c_clean)
                seen.add(c_clean)
                meta.append({
                    "strategy": r.strategy,
                    "original": r.original,
                    "candidate": c_clean,
                    "filters": r.filters if r.filters else None,
                })
            # selfquery 提取的 category filter 合并到 ctx
            if r.strategy == "selfquery" and r.filters:
                if r.filters.get("category") and not ctx.category_filter:
                    ctx.category_filter = r.filters["category"]

        ctx.candidate_queries = candidates
        ctx.rewrite_candidates_meta = meta
        logger.info(
            "Query rewrite: %d strategies -> %d candidates",
            len(ctx.rewrite_strategies), len(candidates),
        )
        return ctx


__all__ = ["QueryRewritePlugin"]
