# -*- coding: utf-8 -*-
"""RAG 文档管理路由（B 端）。

公开接口：
- GET  /api/rag/documents?tenant_id=... -> 列出文档（按 tenant 隔离）

管理员接口（require_staff）：
- POST /api/rag/publish/{document_id} -> 发布/取消发布（body: {is_published: bool}）
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, require_staff
from app.db.models import Document
from app.db.session import get_session

router = APIRouter(prefix="/api", tags=["RAG 文档管理"])


@router.get("/rag/documents", summary="列出知识库文档")
async def list_documents(
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant_id: Optional[str] = None,
) -> List[dict]:
    """列出当前可见的知识库文档（多租户隔离）。

    - 默认只列出当前用户 tenant 的文档
    - tenant_id 显式传可切换（admin 用）
    """
    target_tenant = tenant_id or current.tenant_id
    stmt = select(Document).where(
        Document.tenant_id == target_tenant,
        Document.deleted_at.is_(None),
    ).order_by(Document.created_at.desc())
    rows = (await session.scalars(stmt)).all()
    return [
        {
            "document_id": d.document_id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "page_count": d.page_count,
            "mineru_status": d.mineru_status,
            "is_published": bool(getattr(d, "is_published", False)),
            "published_at": d.published_at.isoformat() if getattr(d, "published_at", None) else None,
            "tenant_id": d.tenant_id,
            "category": d.category,
            "audience": d.audience,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in rows
    ]


@router.get("/rag/documents/{document_id}", summary="文档详情")
async def get_document(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    doc = await session.scalar(select(Document).where(Document.document_id == document_id))
    if doc is None:
        raise HTTPException(404, "文档不存在")
    return {
        "document_id": doc.document_id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "mineru_status": doc.mineru_status,
        "is_published": bool(getattr(doc, "is_published", False)),
        "published_at": doc.published_at.isoformat() if getattr(doc, "published_at", None) else None,
        "tenant_id": doc.tenant_id,
        "category": doc.category,
        "audience": doc.audience,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.post("/rag/publish/{document_id}", summary="发布/取消发布文档")
async def publish_document(
    document_id: str,
    body: dict,
    current: Annotated[CurrentUser, Depends(require_staff)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """发布文档：让 RAG 检索能命中此文档。

    body: {is_published: bool}
    """
    doc = await session.scalar(select(Document).where(Document.document_id == document_id))
    if doc is None:
        raise HTTPException(404, "文档不存在")
    is_pub = bool(body.get("is_published", True))
    doc.is_published = is_pub
    doc.published_at = datetime.now() if is_pub else None
    await session.commit()
    return {
        "status": "ok",
        "document_id": document_id,
        "is_published": doc.is_published,
        "published_at": doc.published_at.isoformat() if doc.published_at else None,
    }


# ==================================================================
# 从 api.py 迁移的 8 个 RAG 端点（统一在 routers/rag.py）
# ==================================================================

@router.get("/rag/supported-formats", summary="返回支持的文件格式")
async def rag_supported_formats(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """P1-2: 加鉴权。借鉴 ekbs: 返回所有支持的格式 (前端 KnowledgePage 上传按钮用)."""
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    from app.rag.parsers import get_supported_extensions
    return {
        "supported": get_supported_extensions(),
        "categories": {
            "document": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".md", ".markdown"],
            "image": [".jpg", ".jpeg", ".png", ".webp", ".bmp"],
            "audio": [".mp3", ".wav", ".m4a", ".ogg", ".flac"],
            "text": [".txt", ".log", ".rst"],
        },
        "max_size_mb": 100,
    }


@router.get("/rag/search", summary="RAG 检索")
async def rag_search(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    query: str,
    tenant_id: str = 'default',
    top_k: int = 5,
    enable_self_rag: bool = True,
) -> dict:
    """RAG 检索接口（支持多租户 + Self-RAG 优化）。"""
    from app.rag.v2_engine import retrieve

    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    if enable_self_rag:
        result = await self_rag_retrieve(query, tenant_id=tenant_id, top_k=top_k)
    else:
        result = await retrieve(query, tenant_id=tenant_id, top_k=top_k)

    return {
        'hits': [
            {
                'source': hit.source,
                'content': hit.content,
                'score': hit.score,
            }
            for hit in result.hits
        ],
        'stats': {
            'retrieval_time_ms': result.retrieval_time_ms,
            'child_hits_count': result.child_hits_count,
            'parent_count': result.parent_count,
            'rerank_applied': result.rerank_applied,
        },
        'tenant_id': tenant_id,
    }



# DEPRECATED: 建议用 routers/rag.py 内同义端点。


@router.post("/rag/index", summary="索引文档")
async def rag_index_document(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
    content: str,
    filename: str,
    tenant_id: str = 'default',
    category: str = 'general',
) -> dict:
    """API 方式索引单个文档。P1-2: 必须 JWT 鉴权。"""
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    from app.rag.v2_engine import index_document
    return await index_document(document_id, content, filename, tenant_id, category)



# DEPRECATED: 建议用 routers/rag.py 内同义端点。


@router.post("/rag/upload", summary="上传文件")
async def rag_upload_document(
    current: Annotated[CurrentUser, Depends(require_staff)],
    file: UploadFile,
    document_id: str = '',
    tenant_id: str = 'default',
    category: str = 'general',
) -> dict:
    """文件上传 + 自动解析 + 索引。P1-2: 必须 JWT 鉴权。"""
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    from app.rag.parsers import get_parser
    from app.rag.parsers.utils import is_safe_url

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    # 保存到临时文件，调用解析器
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        content_bytes = await file.read()
        tmp.write(content_bytes)
        tmp_path = tmp.name
    try:
        parser = get_parser(tmp_path, file.filename)
        # 第 1 层: 文档级校验
        from app.rag.quality.validator import validate_document_level
        doc_v = validate_document_level(
            filename=file.filename, file_size_bytes=len(content_bytes))
        if not doc_v.passed:
            raise HTTPException(status_code=400, detail=doc_v.reason)
        parents = parser.load(
            document_id=document_id or file.filename,
            tenant_id=tenant_id,
            category=category,
        )
        # 第 2 层: 块级校验 (借鉴 ekbs)
        from app.rag.quality.validator import validate_chunk_level
        total_chunks = 0
        skipped = 0
        from app.rag.v2_engine import index_document
        for p in parents:
            for c in p.child_chunks:
                v = validate_chunk_level(c.content)
                if not v.passed:
                    skipped += 1
                    continue
                await index_document(
                    document_id=f"{document_id or file.filename}_chunk_{total_chunks}",
                    content=c.content,
                    filename=file.filename,
                    tenant_id=tenant_id,
                    category=category,
                )
                total_chunks += 1
        return {
            "status": "ok",
            "filename": file.filename,
            "document_id": document_id or file.filename,
            "tenant_id": tenant_id,
            "parents": len(parents),
            "child_chunks_indexed": total_chunks,
            "child_chunks_skipped": skipped,
        }
    finally:
        os.unlink(tmp_path)



# DEPRECATED: 建议用 routers/rag.py 内同义端点。


@router.get("/rag/stats", summary="知识库统计")
async def rag_stats(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    tenant_id: str | None = None,
) -> dict:
    """P1-2: 加鉴权。"""
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    """知识库统计接口（监控面板用）。"""
    from app.rag.v2_engine import get_knowledge_stats
    return await get_knowledge_stats(tenant_id)



# DEPRECATED: 建议用 routers/rag.py 内同义端点。


@router.get("/rag/chunks", summary="列出 chunks")
async def rag_list_chunks(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    document_id: str | None = None,
    tenant_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict:
    """查看向量库里的 chunks（用于调试切分效果）。

    - document_id: 按文档 ID 过滤（可选）
    - tenant_id: 按租户过滤（可选）
    - limit: 返回前 N 条（默认 10）
    - offset: 跳过前 N 条（用于分页）

    返回每个 chunk 的完整 payload（含 content）和元数据。
    """
    # P1-2: 必须 JWT 鉴权（暴露全部 chunks 是数据泄露）
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    # from app.rag.engine import _get_qdrant_client  # removed: Qdrant deprecated
    from app.core.config import vector_store_config
    from qdrant_client import models as qdrant_models

    if vector_store_config.engine != "qdrant-local":
        raise HTTPException(status_code=400, detail="仅 qdrant-local 模式支持此端点")

    client = await _get_qdrant_client()
    must_conditions = []
    if document_id is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="document_id", match=qdrant_models.MatchValue(value=document_id)
            )
        )
    if tenant_id is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="tenant_id", match=qdrant_models.MatchValue(value=tenant_id)
            )
        )
    query_filter = qdrant_models.Filter(must=must_conditions) if must_conditions else None

    results = client.scroll(
        collection_name=vector_store_config.collection,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
        scroll_filter=query_filter,
    )
    points = results[0]

    return {
        "total": len(points),
        "offset": offset,
        "limit": limit,
        "chunks": [
            {
                "id": p.id,
                "filename": (p.payload or {}).get("filename"),
                "document_id": (p.payload or {}).get("document_id"),
                "tenant_id": (p.payload or {}).get("tenant_id"),
                "category": (p.payload or {}).get("category"),
                "content": (p.payload or {}).get("content", ""),
                "content_length": len((p.payload or {}).get("content", "")),
            }
            for p in points
        ],
    }



# DEPRECATED: 建议用 routers/rag.py 内同义端点。


@router.get("/rag/test-recall", summary="测试召回")
async def rag_test_recall(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    query: str,
    top_k: int = 10,
    filename: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """测试召回命中：问一个问题，返回按相关度排序的切片。

    P1-2: 加鉴权。借鉴 ekbs-ai-service 的 `/txt/test` 端点思路：
    - 用户问问题
    - 走完整 RAG 流程（embed + 向量召回 + 多租户 filter）
    - 返回按 score 排序的切片

    Args:
        query: 用户问题
        top_k: 返回前 N 条（默认 10）
        filename: 按文件名过滤（可选）
        tenant_id: 按租户过滤（可选）
    """
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    """

    Returns:
        {
          "query": "...",
          "elapsed_ms": 123,
          "hits": [{ "rank": 1, "score": 0.95, "content": "...", "filename": "...", "document_id": "..." }, ...]
        }
    """
    from app.rag.v2_engine import retrieve
    from app.core.config import vector_store_config

    if not query.strip():
        raise HTTPException(status_code=400, detail="query 必填")

    # 选择 self_rag_retrieve（带反思） 或 retrieve
    if filename or tenant_id:
        # 带过滤条件用 retrieve
        result = await retrieve(
            query=query,
            tenant_id=tenant_id or "default",
            top_k=top_k,
            enable_rerank=False,  # 简化：直接返回向量分数
        )
    else:
        result = await retrieve(
            query=query,
            tenant_id="default",
            top_k=top_k,
            enable_rerank=False,
        )

    # 按 score 排序
    sorted_hits = sorted(result.hits, key=lambda h: h.score, reverse=True)[:top_k]

    # 如果指定 filename 过滤
    if filename:
        sorted_hits = [h for h in sorted_hits if filename in (h.source or "")]

    return {
        "query": query,
        "elapsed_ms": result.retrieval_time_ms,
        "child_hits_count": result.child_hits_count,
        "total_candidates": len(result.hits),
        "hits": [
            {
                "rank": i + 1,
                "score": round(hit.score, 4),
                "content": hit.content,
                "filename": hit.source,
                "tenant_id": hit.tenant_id,
                "parent_id": hit.parent_id,
            }
            for i, hit in enumerate(sorted_hits)
        ],
    }


