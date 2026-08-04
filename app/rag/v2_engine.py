# -*- coding: utf-8 -*-
"""RAG engine v2: parent in business DB / child in Milvus (ekbs design).

Reference: docs/LONG_TERM_MEMORY_EKBS_AI_SERVICE.md
- Child chunk (800 token): Milvus, payload has parent_id reference
- Parent chunk (2000 token): business DB, only stores full text
- Document: meta info only

Index flow:
  chunks -> embed -> parent to DB / child to Milvus

Retrieval flow:
  query -> embed -> Milvus recall child ->
  aggregate by parent_id -> batch query DB for parent -> Rerank -> Top-K
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    parent_id: str
    content: str
    source: str
    score: float
    matched_child: str
    tenant_id: str
    document_id: str = ""


@dataclass
class RetrievalResult:
    hits: List[RetrievalHit]
    retrieval_time_ms: int
    child_hits_count: int
    parent_count: int
    rerank_applied: bool
    tenant_id: str


_milvus_store: Optional[Any] = None


async def get_milvus_store():
    global _milvus_store
    if _milvus_store is not None:
        return _milvus_store
    from app.rag.milvus_store import MilvusStore
    from app.core.config import vector_store_config
    _milvus_store = MilvusStore(
        host=vector_store_config.host or "localhost",
        port=int(os.environ.get("MILVUS_PORT", "19530")),
        collection=vector_store_config.collection or "hairstylist_kb",
        dim=vector_store_config.dims or 1024,
    )
    _milvus_store.ensure_collection()
    return _milvus_store


async def _get_embedding(texts: List[str]) -> List[List[float]]:
    from app.embedding import build_embedding_model
    from agentscope.message import TextBlock
    model = build_embedding_model()
    resp = await model([TextBlock(text=t) for t in texts])
    return resp.embeddings


async def index_document(
    document_id: str,
    content: str,
    filename: str,
    tenant_id: str = "default",
    category: str = "general",
    parent_chunk_size: int = 2000,
    child_chunk_size: int = 800,
    child_chunk_overlap: int = 80,
) -> dict[str, Any]:
    """Index document: parent-child split, dual-write (parent to DB / child to Milvus)."""
    # Late import to avoid circular deps
    from app.rag.chunkers.smart_chunker import (
        build_child_chunks, build_parent_chunks,
        split_markdown_by_heading, extract_qa_pairs, merge_qa_into_chunks,
    )
    from app.db.session import async_session_maker
    from app.db.models import Document, ParentChunk
    from sqlalchemy import select

    start_time = time.time()

    sections = split_markdown_by_heading(content, child_chunk_size, child_chunk_overlap)
    qa_pairs = extract_qa_pairs(content)
    if qa_pairs:
        sections = merge_qa_into_chunks(sections, qa_pairs)

    child_chunks = build_child_chunks(
        sections, source_filename=filename, document_id=document_id,
        tenant_id=tenant_id, category=category,
    )
    parent_chunks = build_parent_chunks(
        child_chunks, parent_chunk_size=parent_chunk_size,
        source_filename=filename, document_id=document_id, tenant_id=tenant_id,
    )

    logger.info(
        "Doc %s split: %d parents / %d children",
        document_id, len(parent_chunks), len(child_chunks),
    )

    if not child_chunks:
        return {"status": "empty", "chunks": 0, "time_ms": 0}

    # 1. Save parents to business DB
    parent_ids: List[str] = []
    async with async_session_maker() as session:
        stmt = select(Document).where(Document.document_id == document_id)
        doc = (await session.execute(stmt)).scalar_one_or_none()
        if not doc:
            doc = Document(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                file_type="pdf",
                mineru_status="indexed",
            )
            session.add(doc)
            await session.flush()
        for pos, p in enumerate(parent_chunks):
            pid = str(uuid.uuid4())
            parent_ids.append(pid)
            session.add(ParentChunk(
                parent_id=pid,
                tenant_id=tenant_id,
                document_id=document_id,
                content=p.content,
                token_num=p.token_num,
                position=pos,
            ))
        await session.commit()

    # 2. Build child -> parent mapping
    child_to_parent_idx: List[int] = []
    for child in child_chunks:
        for pi, p in enumerate(parent_chunks):
            if child in p.child_chunks:
                child_to_parent_idx.append(pi)
                break
        else:
            child_to_parent_idx.append(0)

    # 3. Embed children
    child_texts = [c.content for c in child_chunks]
    vectors = await _get_embedding(child_texts)
    logger.info("Embedded: %d vectors (dim=%d)", len(vectors), len(vectors[0]) if vectors else 0)

    # 4. Insert to Milvus
    ms = await get_milvus_store()
    payloads = []
    for ci, (vec, child) in enumerate(zip(vectors, child_chunks)):
        pi = child_to_parent_idx[ci]
        pid = parent_ids[pi] if pi < len(parent_ids) else ""
        payloads.append({
            "parent_id": pid,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "filename": filename,
            "category": category,
        })
    ms.insert(vectors, payloads)

    elapsed = int((time.time() - start_time) * 1000)
    return {
        "status": "ok",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "parents": len(parent_chunks),
        "children": len(child_chunks),
        "time_ms": elapsed,
    }


async def retrieve(
    query: str,
    tenant_id: str = "default",
    top_k: int = 5,
    fetch_k: int = 20,
    enable_rerank: bool = True,
    category_filter: Optional[List[str]] = None,
) -> RetrievalResult:
    """Two-stage retrieval (multi-tenant isolated).

    Stage 1: Milvus vector recall child chunks Top-FetchK
    Stage 2: aggregate by parent_id -> batch query DB -> Rerank -> Top-K parents
    """
    from app.db.session import async_session_maker
    from app.db.models import ParentChunk
    from sqlalchemy import select

    start_time = time.time()
    ms = await get_milvus_store()

    query_vec = (await _get_embedding([query]))[0]
    child_hits = ms.search(
        query_vec, tenant_id=tenant_id, top_k=fetch_k,
        category_filter=category_filter,
    )
    child_hits_count = len(child_hits)
    logger.info("Milvus recall: %d children (tenant=%s)", child_hits_count, tenant_id)

    # Aggregate by parent_id (take highest score)
    best_by_parent: dict[str, RetrievalHit] = {}
    for hit in child_hits:
        pid = hit["parent_id"]
        if not pid:
            continue
        score = hit["score"]
        if pid not in best_by_parent or score > best_by_parent[pid].score:
            best_by_parent[pid] = RetrievalHit(
                parent_id=pid,
                content="",
                source=hit.get("filename", "unknown"),
                score=score,
                matched_child="",
                tenant_id=tenant_id,
                document_id=hit.get("document_id", ""),
            )

    parent_ids = list(best_by_parent.keys())
    if not parent_ids:
        return RetrievalResult(
            hits=[], retrieval_time_ms=int((time.time() - start_time) * 1000),
            child_hits_count=child_hits_count, parent_count=0,
            rerank_applied=False, tenant_id=tenant_id,
        )

    # Batch query parent contents from business DB
    parent_contents: dict[str, str] = {}
    async with async_session_maker() as session:
        stmt = select(ParentChunk).where(ParentChunk.parent_id.in_(parent_ids))
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            parent_contents[r.parent_id] = r.content

    for pid, hit in best_by_parent.items():
        hit.content = parent_contents.get(pid, "")

    parent_hits = list(best_by_parent.values())
    parent_hits.sort(key=lambda h: h.score, reverse=True)
    parent_hits = parent_hits[: top_k * 2]
    rerank_applied = False

    if enable_rerank and len(parent_hits) > 1:
        try:
            from app.embedding import build_rerank_model
            reranker = build_rerank_model()
            pairs = [[query, h.content[:500]] for h in parent_hits]
            scores_resp = await reranker(pairs)
            for hit, score in zip(parent_hits, scores_resp.scores):
                hit.score = float(score)
            parent_hits.sort(key=lambda h: h.score, reverse=True)
            rerank_applied = True
            logger.info("Rerank done: %d parents", len(parent_hits))
        except Exception as e:
            logger.warning("Rerank failed: %s", e)

    final = parent_hits[:top_k]
    return RetrievalResult(
        hits=final,
        retrieval_time_ms=int((time.time() - start_time) * 1000),
        child_hits_count=child_hits_count,
        parent_count=len(parent_hits),
        rerank_applied=rerank_applied,
        tenant_id=tenant_id,
    )


def reset_state():
    """Reset module state (for tests)."""
    global _milvus_store
    _milvus_store = None
