# -*- coding: utf-8 -*-
"""RecallPlugin: 向量 + BM25 双路召回 + RRF 融合.

职责:
  1. 对每个 candidate query 调 v2_engine.retrieve()
  2. 归一化分数 (normalizer.batch_normalize)
  3. 跨 query RRF 融合 (multi-candidate)
  4. 跨召回类型 RRF 融合 (vector + BM25)

输出:
  - ctx.vector_candidates: 归一化后的 vector hits
  - ctx.bm25_candidates: 归一化后的 BM25 hits
  - ctx.fused_candidates: 跨类型 RRF 融合后的 top N
  - ctx.child_hits_count: 子块召回总数
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class RecallPlugin(Plugin):
    """双路召回 Plugin (Phase 3).

    priority=40
    """

    name = "recall"
    priority = 40

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.gate_decision == "refuse":
            return ctx

        candidates = ctx.candidate_queries or [ctx.message]
        # 优先用 ctx.tenant_id (chat_handler 注入), 缺省 str(user_id) (向后兼容)
        tenant_id = ctx.tenant_id or (str(ctx.user_id) if ctx.user_id else "default")

        # 调底层 v2_engine.retrieve (粗召回, 关掉 rerank, 留到下一阶段)
        from app.rag.v2_engine import retrieve
        all_vector_hits: list = []
        all_bm25_hits: list = []

        for cq in candidates:
            try:
                result = await retrieve(
                    query=cq,
                    tenant_id=tenant_id,
                    top_k=ctx.recall_top_k,
                    enable_rerank=False,  # Rerank 阶段单独做
                    enable_bm25=ctx.enable_bm25,
                    enable_rewrite=False,  # Pipeline 已经在前面做过
                    category_filter=ctx.category_filter,
                    audience_filter=ctx.audience_filter,
                    include_unpublished=ctx.include_unpublished,
                )
                # vector hits: 从 RetrievalResult 还原成 dict
                for h in result.hits:
                    all_vector_hits.append({
                        "parent_id": h.parent_id,
                        "content": h.content,
                        "document_id": h.document_id,
                        "filename": h.source,
                        "score": h.score,
                    })
                # child_hits_count 累加
                ctx.child_hits_count += result.child_hits_count
            except Exception as e:
                logger.warning("Recall: candidate %r failed: %s", cq[:30], e)

        # 归一化 + 跨 query 去重 (按 parent_id 取最高分)
        from app.rag.retriever.normalizer import batch_normalize
        vec_norm = batch_normalize(all_vector_hits, engine_type="milvus_cosine")
        bm25_norm = batch_normalize(all_bm25_hits, engine_type="bm25") if all_bm25_hits else []

        # 跨 query 融合: parent_id 保留最高 normalized_score
        ctx.vector_candidates = _dedup_by_parent(vec_norm)
        ctx.bm25_candidates = _dedup_by_parent(bm25_norm)

        # 跨类型 RRF
        from app.rag.hybrid.bm25_search import rrf_fuse
        ctx.fused_candidates = rrf_fuse(
            ctx.vector_candidates,
            ctx.bm25_candidates,
            k=60,
            vector_weight=0.7,
            bm25_weight=0.3,
        )[:ctx.recall_top_k]

        logger.info(
            "Recall: vec=%d bm25=%d fused=%d child_hits=%d",
            len(ctx.vector_candidates), len(ctx.bm25_candidates),
            len(ctx.fused_candidates), ctx.child_hits_count,
        )
        return ctx


def _dedup_by_parent(hits: list) -> list:
    """按 parent_id 保留最高分."""
    if not hits:
        return []
    best: dict = {}
    for h in hits:
        pid = h.get("parent_id", "")
        if not pid:
            continue
        score = h.get("normalized_score", h.get("score", 0.0))
        if pid not in best or score > best[pid].get("normalized_score", best[pid].get("score", 0)):
            best[pid] = h
    return sorted(
        best.values(),
        key=lambda x: x.get("normalized_score", x.get("score", 0.0)),
        reverse=True,
    )


__all__ = ["RecallPlugin"]
