# -*- coding: utf-8 -*-
"""RAG 模块：父子分块 + 两阶段检索 + 多租户隔离 + Self-RAG。"""
from .engine import (
    index_document,
    retrieve,
    self_rag_retrieve,
    get_knowledge_stats,
    RetrievalHit,
    RetrievalResult,
)

__all__ = [
    "index_document",
    "retrieve",
    "self_rag_retrieve",
    "get_knowledge_stats",
    "RetrievalHit",
    "RetrievalResult",
]
