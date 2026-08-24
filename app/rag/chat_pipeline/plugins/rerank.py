# -*- coding: utf-8 -*-
"""RerankPlugin: BGE Rerank + Enriched Passage.

职责:
  1. 拿 ctx.fused_candidates (top recall_top_k)
  2. 拼 Enriched Passage (文档名/章节/内容)
  3. 调 BGE Rerank
  4. 归一化分数, 排序
  5. 取 top rerank_top_n 进 ctx.reranked_hits
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class RerankPlugin(Plugin):
    """Rerank Plugin (Phase 4).

    priority=50
    """

    name = "rerank"
    priority = 50

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.gate_decision == "refuse":
            return ctx
        if not ctx.enable_rerank:
            # 不开 Rerank, fused_candidates 直接当 reranked
            ctx.reranked_hits = ctx.fused_candidates
            return ctx
        if len(ctx.fused_candidates) <= 1:
            ctx.reranked_hits = ctx.fused_candidates
            return ctx

        try:
            from app.embedding import build_rerank_model
            from app.rag.chat_pipeline.enrich import (
                get_enriched_passage,
                sanitize_passage_for_rerank,
            )
            from app.rag.retriever.normalizer import normalize_score

            reranker = build_rerank_model()
            passages = []
            for h in ctx.fused_candidates[:ctx.rerank_top_n * 2]:
                passage = get_enriched_passage(
                    h, max_chars=1500,
                )
                passage = sanitize_passage_for_rerank(passage)
                passages.append(passage)

            scores_resp = await reranker(
                [[ctx.message, p] for p in passages]
            )

            hits = list(ctx.fused_candidates[:len(passages)])
            for hit, score in zip(hits, scores_resp.scores):
                hit["rerank_score"] = normalize_score(
                    float(score), engine_type="rerank",
                )
            hits.sort(key=lambda h: h.get("rerank_score", 0), reverse=True)
            ctx.reranked_hits = hits[:ctx.rerank_top_n]
            ctx.rerank_applied = True
            logger.info(
                "Rerank done: %d -> top %d (top1=%.3f)",
                len(ctx.fused_candidates), len(ctx.reranked_hits),
                ctx.reranked_hits[0].get("rerank_score", 0) if ctx.reranked_hits else 0,
            )
        except Exception as e:
            logger.warning("Rerank failed, use fused order: %s", e)
            ctx.reranked_hits = ctx.fused_candidates[:ctx.rerank_top_n]

        return ctx


__all__ = ["RerankPlugin"]
