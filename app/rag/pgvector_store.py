# -*- coding: utf-8 -*-
"""pgvector 适配器 (替代 MilvusStore, 接口等价).

设计:
- 单表 child_chunks 存所有子块 (vector + payload)
- 向量检索: 1 - (embedding <=> query_vec) 作为 cosine 相似度
- 多租户 / 受众 / 类别 过滤: 标量 WHERE
- 删除: 按 document_id 批量删 (单事务)

接口兼容 MilvusStore (v2_engine.py 调用方零改动):
- insert(vectors, payloads) -> List[str]
- search(query_vec, tenant_id, ...) -> List[dict]
- delete_by_document(document_id, tenant_id) -> int
- count(tenant_id) -> int
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# 字段名常量 (与 MilvusStore 保持一致)
PARENT_ID_KEY = "parent_id"
TENANT_ID_KEY = "tenant_id"
DOCUMENT_ID_KEY = "document_id"
FILENAME_KEY = "filename"
CATEGORY_KEY = "category"
AUDIENCE_KEY = "audience"
IS_PUBLISHED_KEY = "is_published"
IMAGE_PATH_KEY = "image_path"
CONTENT_KEY = "content"


class PgvectorStore:
    """pgvector 适配器 (生产级, 替代 MilvusStore)."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        collection: str = "child_chunks",
        dim: int = 1024,
        metric_type: str = "COSINE",
    ):
        self.host = host
        self.port = port
        self.collection = collection
        self.dim = dim
        self.metric_type = metric_type

    def ensure_collection(self) -> None:
        """空操作: schema 由 alembic 0011 管理."""
        logger.info("PgvectorStore: schema 由 alembic 0011 管理, 无需 ensure")

    async def insert(self, vectors, payloads):
        """批量插入子块到 child_chunks."""
        if not vectors:
            return []
        if len(vectors) != len(payloads):
            raise ValueError(f"vectors ({len(vectors)}) 和 payloads ({len(payloads)}) 数量不匹配")

        from app.db.models import ChildChunk
        from app.db.session import async_session_maker

        rows = []
        child_ids = []
        for vec, p in zip(vectors, payloads):
            cid = str(uuid.uuid4())
            child_ids.append(cid)
            rows.append(ChildChunk(
                child_id=cid,
                parent_id=str(p.get(PARENT_ID_KEY, "")),
                tenant_id=str(p.get(TENANT_ID_KEY, "default")),
                document_id=str(p.get(DOCUMENT_ID_KEY, "")),
                filename=str(p.get(FILENAME_KEY, "unknown")),
                category=str(p.get(CATEGORY_KEY, "general")),
                audience=str(p.get(AUDIENCE_KEY, "all")),
                is_published=bool(p.get(IS_PUBLISHED_KEY, False)),
                image_path=p.get(IMAGE_PATH_KEY),
                content=p.get(CONTENT_KEY, ""),
                embedding=vec,
            ))

        from app.db.session import async_session_maker
        async with async_session_maker() as session:
            session.add_all(rows)
            await session.commit()

        logger.info("Pgvector insert: %d 子块", len(rows))
        return child_ids

    async def search(
        self,
        query_vector,
        tenant_id,
        top_k=20,
        category_filter=None,
        document_id_filter=None,
        audience_filter=None,
        include_unpublished=False,
    ):
        """向量检索 (HNSW) + 标量过滤 (一个 SQL)."""
        from app.db.models import ChildChunk, Document
        from sqlalchemy import select, and_

        from app.db.session import async_session_maker
        async with async_session_maker() as session:
            dist = ChildChunk.embedding.cosine_distance(query_vector)
            sim = (1 - dist).label("score")

            stmt = select(ChildChunk, sim).where(ChildChunk.tenant_id == tenant_id)

            if audience_filter:
                stmt = stmt.where(ChildChunk.audience.in_(audience_filter))
            if category_filter:
                stmt = stmt.where(ChildChunk.category.in_(category_filter))
            if document_id_filter:
                stmt = stmt.where(ChildChunk.document_id == document_id_filter)

            if not include_unpublished:
                stmt = stmt.join(
                    Document, ChildChunk.document_id == Document.document_id
                )
                stmt = stmt.where(
                    and_(Document.is_published == True, Document.deleted_at.is_(None))  # noqa: E712
                )

            stmt = stmt.order_by(dist).limit(top_k)
            rows = (await session.execute(stmt)).all()

        return [
            {
                "id": r.ChildChunk.child_id,
                "score": float(r.score),
                "parent_id": r.ChildChunk.parent_id,
                "tenant_id": r.ChildChunk.tenant_id,
                "document_id": r.ChildChunk.document_id,
                "filename": r.ChildChunk.filename,
                "category": r.ChildChunk.category,
                "audience": r.ChildChunk.audience,
                "image_path": r.ChildChunk.image_path,
                "content": r.ChildChunk.content,
            }
            for r in rows
        ]

    async def delete_by_document(self, document_id, tenant_id):
        """按 document_id 删除."""
        from app.db.models import ChildChunk
        from sqlalchemy import delete

        from app.db.session import async_session_maker
        async with async_session_maker() as session:
            result = await session.execute(
                delete(ChildChunk).where(
                    ChildChunk.document_id == document_id,
                    ChildChunk.tenant_id == tenant_id,
                )
            )
            await session.commit()
            count = result.rowcount
        logger.info("Pgvector delete: %s -> %d 子块", document_id, count)
        return count

    async def count(self, tenant_id=None):
        """统计子块数."""
        from app.db.models import ChildChunk
        from sqlalchemy import select, func

        async with async_session_maker() as session:
            stmt = select(func.count(ChildChunk.id))
            if tenant_id:
                stmt = stmt.where(ChildChunk.tenant_id == tenant_id)
            cnt = (await session.execute(stmt)).scalar() or 0
        return cnt

    async def get_collection_stats(self):
        """获取表统计."""
        from app.db.models import ChildChunk
        from sqlalchemy import select, func, text

        from app.db.session import async_session_maker
        async with async_session_maker() as session:
            cnt = (await session.execute(select(func.count(ChildChunk.id)))).scalar() or 0
            try:
                size_result = await session.execute(text(
                    "SELECT pg_size_pretty(pg_total_relation_size(''child_chunks''))"
                ))
                size = size_result.scalar() or "unknown"
            except Exception:
                size = "unknown"
        return {
            "collection": self.collection,
            "row_count": cnt,
            "dim": self.dim,
            "size": size,
            "engine": "pgvector",
        }


__all__ = [
    "PgvectorStore",
    "PARENT_ID_KEY", "TENANT_ID_KEY", "DOCUMENT_ID_KEY",
    "FILENAME_KEY", "CATEGORY_KEY", "AUDIENCE_KEY",
    "IS_PUBLISHED_KEY", "IMAGE_PATH_KEY", "CONTENT_KEY",
]
