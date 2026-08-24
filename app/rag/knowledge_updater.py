# -*- coding: utf-8 -*-
"""KnowledgeUpdater: 文档变更事件 -> 增量更新."""
from __future__ import annotations
import hashlib, logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ChangeEvent:
    document_id: str
    content: str
    filename: str
    tenant_id: str
    audience: str = "all"
    category: str = "general"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_model_version: str = "1.0"
    chunk_strategy: str = "smart"
    chunk_size: int = 800
    chunk_overlap: int = 80
    actor_id: Optional[int] = None
    actor_type: str = "system"


@dataclass
class UpdateResult:
    action: str
    document_id: str
    version_id: int = 0
    content_hash: str = ""
    reason: str = ""
    parents: int = 0
    children: int = 0
    latency_ms: int = 0
    error: Optional[str] = None


class KnowledgeUpdater:
    @staticmethod
    def compute_hash(content):
        return hashlib.sha256((content or "").encode("utf-8", errors="ignore")).hexdigest()

    async def on_document_changed(self, event):
        import time
        t0 = time.time()
        new_hash = self.compute_hash(event.content)
        try:
            from app.db.session import async_session_maker
            from app.db.models import Document
            from sqlalchemy import select, update
            async with async_session_maker() as session:
                stmt = select(Document).where(
                    Document.tenant_id == event.tenant_id,
                    Document.content_hash == new_hash,
                    Document.is_deleted == False,
                )
                existing_same_hash = (await session.execute(stmt)).scalars().first()
                if existing_same_hash and existing_same_hash.document_id != event.document_id:
                    return UpdateResult(
                        action="skipped", document_id=event.document_id,
                        content_hash=new_hash,
                        reason="same_hash_exists:" + existing_same_hash.document_id,
                        latency_ms=int((time.time() - t0) * 1000),
                    )
                stmt = select(Document).where(Document.document_id == event.document_id)
                existing = (await session.execute(stmt)).scalars().first()
                if existing:
                    if existing.content_hash == new_hash:
                        return UpdateResult(action="skipped", document_id=event.document_id, content_hash=new_hash, reason="no_change", latency_ms=int((time.time() - t0) * 1000))
                    await session.execute(update(Document).where(Document.document_id == event.document_id).values(is_deleted=True, deleted_at=datetime.now()))
                    new_version = (existing.version_id or 1) + 1
                    logger.info("soft-delete old version=%d doc=%s", existing.version_id, event.document_id)
                else:
                    new_version = 1
                new_doc = Document(document_id=event.document_id, tenant_id=event.tenant_id, filename=event.filename, audience=event.audience, category=event.category, content_hash=new_hash, version_id=new_version, is_deleted=False, deleted_at=None, chunk_strategy=event.chunk_strategy, chunk_size=event.chunk_size, chunk_overlap=event.chunk_overlap, embedding_model=event.embedding_model, embedding_model_version=event.embedding_model_version, mineru_status="indexing")
                session.add(new_doc)
                await session.commit()
            index_result = await self._index(event)
            return UpdateResult(action="updated" if existing else "created", document_id=event.document_id, version_id=new_version, content_hash=new_hash, parents=index_result.get("parents", 0), children=index_result.get("children", 0), latency_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            logger.exception("KnowledgeUpdater failed: %s", e)
            return UpdateResult(action="error", document_id=event.document_id, content_hash=new_hash, error=type(e).__name__ + ": " + str(e), latency_ms=int((time.time() - t0) * 1000))

    async def soft_delete(self, document_id, tenant_id, actor_id=None):
        from app.db.session import async_session_maker
        from app.db.models import Document
        from sqlalchemy import update
        try:
            async with async_session_maker() as session:
                result = await session.execute(update(Document).where(Document.document_id == document_id, Document.tenant_id == tenant_id).values(is_deleted=True, deleted_at=datetime.now()))
                await session.commit()
                if result.rowcount == 0:
                    return UpdateResult(action="error", document_id=document_id, reason="not_found", error="document not found")
            from app.rag.v2_engine import get_vector_store
            try:
                vs = await get_vector_store()
                if hasattr(vs, "delete_by_document"):
                    await vs.delete_by_document(document_id, tenant_id)
            except Exception as e:
                logger.warning("Vector store delete failed: %s", e)
            return UpdateResult(action="soft_deleted", document_id=document_id, reason="marked_deleted")
        except Exception as e:
            return UpdateResult(action="error", document_id=document_id, error=type(e).__name__ + ": " + str(e))

    async def _index(self, event):
        from app.rag.v2_engine import index_document
        return await index_document(document_id=event.document_id, content=event.content, filename=event.filename, tenant_id=event.tenant_id, category=event.category, audience=event.audience, parent_chunk_size=event.chunk_size * 2, child_chunk_size=event.chunk_size, child_chunk_overlap=event.chunk_overlap)


_updater = None


def get_knowledge_updater():
    global _updater
    if _updater is None:
        _updater = KnowledgeUpdater()
    return _updater


__all__ = ["ChangeEvent", "KnowledgeUpdater", "UpdateResult", "get_knowledge_updater"]
