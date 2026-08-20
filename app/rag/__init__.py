# -*- coding: utf-8 -*-
"""RAG 模块：父子分块 + 两阶段检索 + 多租户隔离 + Self-RAG。"""
from app.rag.v2_engine import (
    index_document,
    retrieve,
    reset_state,
    get_vector_store,
    get_milvus_store,  # 向后兼容, 已弃用, 请改用 get_vector_store
)
from app.rag.v2_engine import (
    RetrievalHit,
    RetrievalResult,
)

__all__ = [
    "index_document",
    "retrieve",
    "reset_state",
    "get_vector_store",
    "get_milvus_store",  # deprecated
    "RetrievalHit",
    "RetrievalResult",
]
