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

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user, require_staff
from app.db.models import Document
from app.db.session import async_session_maker, get_session

router = APIRouter(prefix="/api", tags=["RAG 文档管理"])


# ==================================================================
# 状态机辅助函数 (P0-3: 统一文档状态切换入口)
# ==================================================================
async def _set_doc_status(
    document_id: str,
    new_status: str,
    page_count: int | None = None,
) -> None:
    """统一修改文档状态 (用新 session 避免 detached 问题).

    不校验状态机合法性 (由调用方保证, 这样可以从任何状态强制切到终态如 failed).
    """
    from app.db.models import Document
    from sqlalchemy import select

    async with async_session_maker() as session:
        doc = await session.scalar(select(Document).where(Document.document_id == document_id))
        if doc is None:
            return
        doc.mineru_status = new_status
        if page_count is not None:
            doc.page_count = page_count
        await session.commit()


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
    # P1 修复: CurrentUser 没有 tenant_id 属性, 用 'default' 作默认租户
    target_tenant = tenant_id or "default"
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

    校验:
      - 只有 mineru_status=indexed 才能发布
      - 取消发布无限制 (任何状态都可)
    """
    doc = await session.scalar(select(Document).where(Document.document_id == document_id))
    if doc is None:
        raise HTTPException(404, "文档不存在")
    is_pub = bool(body.get("is_published", True))
    if is_pub and doc.mineru_status != "indexed":
        raise HTTPException(
            status_code=400,
            detail=f"文档状态为「{doc.mineru_status}」，必须先解析完成 (indexed) 才能发布",
        )
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


@router.post("/rag/upload", summary="上传文件 (仅保存, 不解析)")
async def rag_upload_document(
    current: Annotated[CurrentUser, Depends(require_staff)],
    file: UploadFile,
    document_id: str = '',
    tenant_id: str = 'default',
    category: str = Form('general', description="知识库组别 (perming/cutting/coloring/care/general)"),
) -> dict:
    """文件上传 → 创建 Document 记录 (status=pending), 不解析不入库。

    业务流程 (P0-3: 拆分上传和解析):
      1. 上传: 本接口 (保存到 data/uploads/, 创建 Document: pending)
      2. 解析: POST /api/rag/parse/{document_id} (用户在前端点「开始学习」)
      3. 查看切块: GET  /api/rag/documents/{document_id}/chunks
      4. 发布:     POST /api/rag/publish/{document_id}  (RAG 才能召回)

    重新设计原因: 之前一锅端, 文档量大会超时; 失败时无法定位是哪步失败。
    """
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    from app.rag.quality.validator import validate_document_level

    content_bytes = await file.read()
    file_size = len(content_bytes)

    # 文档级校验
    doc_v = validate_document_level(filename=file.filename, file_size_bytes=file_size)
    if not doc_v.passed:
        raise HTTPException(status_code=400, detail=doc_v.reason)

    # 生成 document_id (优先用前端传的, 否则用 uuid)
    import os, uuid
    from pathlib import Path

    doc_id = document_id.strip() or f"doc-{uuid.uuid4().hex[:12]}"
    file_ext = os.path.splitext(file.filename)[1].lower()
    # 保存到 data/uploads/ (相对项目根)
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}{file_ext}"
    file_path.write_bytes(content_bytes)

    # 创建 Document 记录 (status=pending)
    from app.db.models import Document
    from app.db.session import get_session
    from sqlalchemy import select
    from datetime import datetime

    async with async_session_maker() as session:
        try:
            existing = await session.scalar(select(Document).where(Document.document_id == doc_id))
            if existing:
                # 已存在: 覆盖式更新 (允许重传)
                existing.filename = file.filename
                existing.file_size = file_size
                existing.file_type = file_ext.lstrip(".") or "txt"
                existing.mineru_status = "pending"
                existing.is_published = False
                existing.published_at = None
                existing.page_count = 0
                existing.category = category
                existing.tenant_id = tenant_id
            else:
                session.add(Document(
                    document_id=doc_id,
                    tenant_id=tenant_id,
                    filename=file.filename,
                    file_size=file_size,
                    file_type=file_ext.lstrip(".") or "txt",
                    mineru_status="pending",
                    audience="all",
                    category=category,
                ))
            await session.commit()
        finally:
            pass  # async with 自动关闭

    return {
        "status": "ok",
        "document_id": doc_id,
        "filename": file.filename,
        "file_size": file_size,
        "file_type": file_ext.lstrip(".") or "txt",
        "mineru_status": "pending",
        "tenant_id": tenant_id,
        "category": category,
        "message": "文档已上传, 请点「开始学习」触发解析",
    }


@router.post("/rag/parse/{document_id}", summary="解析文档 (切块 + embedding)")
async def rag_parse_document(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
) -> dict:
    """解析已上传的文档: 读取 data/uploads/{document_id} → 切块 → embedding → 入 pgvector.

    业务流程第 2 步 (P0-3): 用户在前端点「开始学习」时调用。
    """
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")

    import os
    from pathlib import Path
    from app.db.models import Document, ParentChunk
    from app.db.enums import DocumentStatus, can_transition_doc
    from app.db.session import get_session
    from sqlalchemy import select, delete

    # ========== 状态机: pending/failed → parsing → indexed/failed ==========
    # 单一职责: 状态切换都走这里, 任何异常都会安全回到 failed 终态

    # 阶段 1: 查 Document + 状态机校验 + 切到 parsing
    async with async_session_maker() as session:
        doc = await session.scalar(select(Document).where(Document.document_id == document_id))
        if doc is None:
            raise HTTPException(404, f"文档 {document_id} 不存在")

        current_status = doc.mineru_status
        if current_status == DocumentStatus.INDEXED.value:
            return {"status": "already_indexed", "message": "文档已解析过, 无需重复"}

        # 状态机校验: 只允许 pending / failed → parsing
        if not can_transition_doc(current_status, DocumentStatus.PARSING.value):
            raise HTTPException(
                status_code=400,
                detail=f"状态机不允许: {current_status} → parsing (请等待当前解析完成)",
            )

        # 切到 parsing + 取消发布 (P0-3: 重新解析强制取消, 避免数据不一致)
        doc.mineru_status = DocumentStatus.PARSING.value
        if doc.is_published:
            doc.is_published = False
            doc.published_at = None
        await session.commit()

    # 阶段 2: 找文件 (用 Path, 不依赖 session)
    upload_dir = Path("data/uploads")
    file_path = None
    for p in upload_dir.iterdir():
        if p.stem == document_id:
            file_path = p
            break
    if file_path is None:
        # 切到 failed (走状态机)
        await _set_doc_status(document_id, DocumentStatus.FAILED.value)
        raise HTTPException(404, f"找不到文档文件: {document_id}")

    # 阶段 3: 解析 + 切块 (try/except 包裹, 任何异常 → failed)
    try:
        from app.rag.parsers import get_parser
        parser = get_parser(str(file_path), doc.filename)
        parents = parser.load(
            document_id=document_id,
            tenant_id=doc.tenant_id,
            category=doc.category,
        )

        if not parents:
            # 空文档: 直接切到 indexed (没东西可入向量库, 但状态是终态)
            await _set_doc_status(document_id, DocumentStatus.INDEXED.value, page_count=0)
            return {"status": "empty", "parents": 0, "children": 0, "message": "文档无内容"}

        # 清掉旧 chunks (允许重新解析)
        async with async_session_maker() as session:
            await session.execute(
                delete(ParentChunk).where(ParentChunk.document_id == document_id)
            )
            await session.commit()

        # 块级校验 + 入库 (parent → PG, child → pgvector, P2-基础设施)
        from app.rag.quality.validator import validate_chunk_level
        from app.rag.v2_engine import index_document

        total_parents = 0
        total_children = 0
        skipped = 0
        for p in parents:
            valid_children = []
            for c in p.child_chunks:
                v = validate_chunk_level(c.content)
                if v.passed:
                    valid_children.append(c)
                else:
                    skipped += 1
            if not valid_children:
                continue
            combined = "\n\n".join(c.content for c in valid_children)
            await index_document(
                document_id=document_id,
                content=combined,
                filename=doc.filename,
                tenant_id=doc.tenant_id,
                category=doc.category,
                audience=doc.audience or "all",
            )
            total_parents += 1
            total_children += len(valid_children)

        # 切到 indexed (状态机终态)
        await _set_doc_status(document_id, DocumentStatus.INDEXED.value, page_count=len(parents))

    except HTTPException:
        raise  # 重新抛 HTTPException
    except Exception as e:  # noqa: BLE001
        # 任何异常 → failed 终态
        await _set_doc_status(document_id, DocumentStatus.FAILED.value)
        raise HTTPException(status_code=500, detail=f"解析失败: {e!s}")

    return {
        "status": "ok",
        "document_id": document_id,
        "mineru_status": DocumentStatus.INDEXED.value,
        "parents": total_parents,
        "children": total_children,
        "skipped": skipped,
    }


@router.post("/rag/reset/{document_id}", summary="重置卡住的文档状态 (admin 救场用)")
async def reset_document_status(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
) -> dict:
    """把卡在 parsing/failed 的文档强制重置为 pending (允许重新解析).

    使用场景:
      - 解析过程中服务被 kill, 文档卡在 parsing
      - 解析失败但状态没正确更新

    强校验: 只允许 parsing/failed → pending (避免误把 indexed 文档重置)
    """
    from app.db.enums import DocumentStatus, can_transition_doc
    from app.db.models import Document
    from sqlalchemy import select

    async with async_session_maker() as session:
        doc = await session.scalar(select(Document).where(Document.document_id == document_id))
        if doc is None:
            raise HTTPException(404, f"文档 {document_id} 不存在")
        if not can_transition_doc(doc.mineru_status, DocumentStatus.PENDING.value):
            raise HTTPException(
                status_code=400,
                detail=f"状态机不允许: {doc.mineru_status} → pending (此操作只用于救场)",
            )
        doc.mineru_status = DocumentStatus.PENDING.value
        if doc.is_published:
            doc.is_published = False
            doc.published_at = None
        await session.commit()

    return {
        "status": "ok",
        "document_id": document_id,
        "mineru_status": DocumentStatus.PENDING.value,
        "message": "已重置为 pending, 可重新解析",
    }


@router.get("/rag/documents/{document_id}/chunks", summary="查看文档的 parent_chunks")
async def get_document_chunks(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """列出某文档的所有 parent_chunks (从 PG)。用于前端查看切块效果。

    注: pgvector child_chunks 表存子块 (更小), parent_chunks 已经够展示.
    """
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")

    from app.db.models import ParentChunk
    from app.db.session import get_session
    from sqlalchemy import select, func

    async with async_session_maker() as session:
        try:
            # 计数
            total = await session.scalar(
                select(func.count(ParentChunk.parent_id))
                .where(ParentChunk.document_id == document_id)
            ) or 0
            # 查内容
            stmt = (
                select(
                    ParentChunk.parent_id, ParentChunk.content,
                    ParentChunk.token_num, ParentChunk.position,
                )
                .where(ParentChunk.document_id == document_id)
                .order_by(ParentChunk.position)
                .limit(limit).offset(offset)
            )
            rows = (await session.execute(stmt)).all()
            return {
                "document_id": document_id,
                "total": total,
                "limit": limit,
                "offset": offset,
                "chunks": [
                    {
                        "parent_id": r.parent_id,
                        "position": r.position,
                        "token_num": r.token_num,
                        "content": r.content,
                        "preview": r.content[:120] + ("…" if len(r.content) > 120 else ""),
                    } for r in rows
                ],
            }
        finally:
            pass  # async with 自动关闭


@router.delete("/rag/documents/{document_id}", summary="删除文档")
async def delete_document(
    document_id: str,
    current: Annotated[CurrentUser, Depends(require_staff)],
) -> dict:
    """删除文档: 删 PG (Document + ParentChunk) + Milvus 向量 + 磁盘文件。"""
    if current is None:
        raise HTTPException(status_code=401, detail="缺少身份认证")

    import os
    from pathlib import Path
    from app.db.models import Document, ParentChunk
    from app.db.session import get_session
    from sqlalchemy import select, delete

    async with async_session_maker() as session:
        try:
            doc = await session.scalar(select(Document).where(Document.document_id == document_id))
            if doc is None:
                raise HTTPException(404, "文档不存在")
            # 删 PG 记录
            await session.execute(delete(ParentChunk).where(ParentChunk.document_id == document_id))
            await session.delete(doc)
            await session.commit()
        finally:
            pass  # async with 自动关闭

    # 删磁盘文件
    upload_dir = Path("data/uploads")
    for p in upload_dir.iterdir():
        if p.stem == document_id:
            try:
                p.unlink()
            except OSError:
                pass
            break

    # 删 pgvector 向量 (P2-基础设施: 替代 Milvus)
    try:
        from app.rag.v2_engine import get_vector_store
        vs = await get_vector_store()
        # 注: 旧数据每个 chunk 是独立 document_id, 需要分别删
        await vs.delete_by_document(document_id, tenant_id or "default")
    except Exception as e:  # noqa: BLE001
        # pgvector 失败不回滚 (PG 已删, 向量变孤儿, 但下次清理会清掉)
        import logging
        logging.warning("pgvector cleanup failed for %s: %s", document_id, e)

    return {"status": "ok", "deleted": document_id}



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

    # P0-3 修复: 启用完整 hybrid + rerank 链路
    # Stage 1: 向量召回 (pgvector) + BM25 召回 (PG tsvector) -> RRF 融合
    # Stage 2: 按 parent_id 聚合 -> 批量查 DB
    # Stage 3: BAAI/bge-reranker-v2-m3 重排序 -> 取 Top-K
    # 注: enable_rewrite=False (提速, LLM 多策略改写单查询 13s, 体验差)
    if filename or tenant_id:
        result = await retrieve(
            query=query,
            tenant_id=tenant_id or "default",
            top_k=top_k,
            enable_rerank=True,   # 硅基流动 BAAI reranker
            enable_bm25=True,     # PG tsvector BM25
            enable_rewrite=False, # 默认关闭 (多策略改写慢)
        )
    else:
        result = await retrieve(
            query=query,
            tenant_id="default",
            top_k=top_k,
            enable_rerank=True,
            enable_bm25=True,
            enable_rewrite=False,
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
        "retrieval_method": {
            "vector": "pgvector (BAAI/bge-large-zh-v1.5, 1024 dim, HNSW)",
            "bm25": "PG tsvector (jieba 分词)",
            "fusion": "RRF (Reciprocal Rank Fusion)",
            "rerank": "BAAI/bge-reranker-v2-m3 (硅基流动 API)",
            "rewrite": "multi-strategy (hyde/step_back/query_rewrite)",
        },
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




# ==================================================================
# P2-基础设施: pgvector 可视化端点 (替代 Attu)
# ==================================================================

@router.get("/rag/inspect", summary="pgvector 可视化 (替代 Attu)")
async def rag_inspect(
    current: Annotated[CurrentUser, Depends(require_staff)],
    doc_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    sample_embedding: bool = False,
) -> dict:
    """pgvector 检视端点 (P2-基础设施, 替代 Milvus Attu).

    用法:
      GET /api/rag/inspect                           -> 知识库全局统计
      GET /api/rag/inspect?doc_id=xxx                -> 某文档的所有 child_chunks
      GET /api/rag/inspect?tenant_id=xxx             -> 某 tenant 的统计
      GET /api/rag/inspect?sample_embedding=true     -> 包含前 5 维 embedding (调试用)

    返回:
      - stats: 全局统计 (chunk 数, 文档数, 表大小, HNSW 索引)
      - chunks: child_chunks 列表 (前 50 个)
    """
    from app.db.models import ChildChunk, Document
    from app.db.session import async_session_maker
    from sqlalchemy import select, func, text

    target_tenant = tenant_id or getattr(current, "tenant_id", None) or "default"

    async with async_session_maker() as s:
        # 1. 全局统计
        stats_queries = {
            "total_chunks": select(func.count(ChildChunk.id)),
            "total_documents": select(func.count(Document.id)).where(Document.deleted_at.is_(None)),
            "published_documents": select(func.count(Document.id)).where(
                Document.is_published == True,  # noqa: E712
                Document.deleted_at.is_(None),
            ),
            "by_tenant": select(
                ChildChunk.tenant_id, func.count(ChildChunk.id).label("cnt")
            ).group_by(ChildChunk.tenant_id),
            "by_category": select(
                ChildChunk.category, func.count(ChildChunk.id).label("cnt")
            ).group_by(ChildChunk.category),
            "by_audience": select(
                ChildChunk.audience, func.count(ChildChunk.id).label("cnt")
            ).group_by(ChildChunk.audience),
        }
        stats = {}
        for key, q in stats_queries.items():
            if "by_" in key:
                rows = (await s.execute(q)).all()
                stats[key] = [{"key": r[0], "count": r[1]} for r in rows]
            else:
                stats[key] = (await s.execute(q)).scalar() or 0

        # 2. 表大小 (HNSW 索引)
        try:
            size_row = (await s.execute(text(
                "SELECT pg_size_pretty(pg_total_relation_size('child_chunks'))"
            ))).scalar()
            stats["table_size"] = size_row or "unknown"
        except Exception:
            stats["table_size"] = "unknown"

        # 3. HNSW 索引状态
        try:
            idx_rows = (await s.execute(text("""
                SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass))
                FROM pg_indexes
                WHERE tablename = 'child_chunks'
            """))).all()
            stats["indexes"] = [{"name": r[0], "size": r[1]} for r in idx_rows]
        except Exception:
            stats["indexes"] = []

        # 4. 详细 chunks
        stmt = select(
            ChildChunk.child_id, ChildChunk.parent_id, ChildChunk.tenant_id,
            ChildChunk.document_id, ChildChunk.filename, ChildChunk.category,
            ChildChunk.audience, ChildChunk.is_published, ChildChunk.image_path,
            ChildChunk.content,
        )
        if doc_id:
            stmt = stmt.where(ChildChunk.document_id == doc_id)
        if tenant_id:
            stmt = stmt.where(ChildChunk.tenant_id == tenant_id)
        stmt = stmt.order_by(ChildChunk.created_at.desc()).limit(limit)
        chunk_rows = (await s.execute(stmt)).all()

        chunks = []
        for r in chunk_rows:
            item = {
                "child_id": r.child_id,
                "parent_id": r.parent_id,
                "tenant_id": r.tenant_id,
                "document_id": r.document_id,
                "filename": r.filename,
                "category": r.category,
                "audience": r.audience,
                "is_published": r.is_published,
                "image_path": r.image_path,
                "content_preview": (r.content or "")[:200] if r.content else "",
                "content_length": len(r.content or ""),
            }
            if sample_embedding:
                # 包含前 5 维 (调试 embedding 维度用, 不暴露全量)
                emb_row = (await s.execute(text(
                    "SELECT embedding::text FROM child_chunks WHERE child_id = :cid"
                ), {"cid": r.child_id})).scalar()
                if emb_row:
                    # embedding 格式 "[0.1,0.2,...]" 取前 5 个
                    dims = emb_row.strip("[]").split(",")[:5]
                    item["embedding_first_5_dims"] = [float(d) for d in dims]
                    item["embedding_dim"] = len(emb_row.strip("[]").split(","))
            chunks.append(item)

    return {
        "engine": "pgvector",  # P2-基础设施
        "stats": stats,
        "chunks": chunks,
        "limit": limit,
        "doc_id": doc_id,
        "tenant_id": target_tenant,
    }
