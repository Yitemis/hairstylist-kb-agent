"""Chat Pipeline: 插件式事件驱动的 RAG + 答案生成管道.

借鉴 WeKnora chat_pipeline/ (Section 4).
"""
from app.rag.chat_pipeline.enrich import (
    DEFAULT_PASSAGE_MAX_CHARS,
    RERANK_SAFETY_MAX_CHARS,
    get_enriched_passage,
    get_enriched_passages_batch,
    sanitize_passage_for_rerank,
)

__all__ = [
    "DEFAULT_PASSAGE_MAX_CHARS",
    "RERANK_SAFETY_MAX_CHARS",
    "get_enriched_passage",
    "get_enriched_passages_batch",
    "sanitize_passage_for_rerank",
]
