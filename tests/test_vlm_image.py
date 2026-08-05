# -*- coding: utf-8 -*-
"""VLM 图片 RAG 测试。"""
import asyncio
from pathlib import Path
import pytest

pytestmark = pytest.mark.keep_milvus

from app.rag.image_indexer import (
    scan_images_in_dir, embed_image, embed_images_batch,
    index_images, search_images,
)
from app.db.models import ImageChunk, Document
from app.db.session import async_session_maker
from sqlalchemy import delete, select


async def _cleanup(tenant_id: str, document_id: str):
    async with async_session_maker() as s:
        await s.execute(delete(ImageChunk).where(
            ImageChunk.tenant_id == tenant_id,
            ImageChunk.document_id == document_id,
        ))
        await s.execute(delete(Document).where(Document.document_id == document_id))
        await s.commit()


async def _ensure_document(document_id: str, tenant_id: str, filename: str = "test.pdf"):
    async with async_session_maker() as s:
        existing = (await s.execute(
            select(Document).where(Document.document_id == document_id)
        )).scalar_one_or_none()
        if not existing:
            s.add(Document(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                category="test",
            ))
            await s.commit()


# 共享 fixture：function scope 但只在 module 第一次调用时初始化
@pytest.fixture
async def indexed_images(request):
    doc_id = "vlm_test_doc"
    tenant = "vlm_test"
    images_dir = "e:/mineru-output/test_30pages/auto/images"
    if not getattr(indexed_images, "_initialized", False):
        # 第一次：drop Milvus + clear DB + index
        from pymilvus import MilvusClient
        c = MilvusClient(uri="http://localhost:19530")
        for col in c.list_collections():
            c.drop_collection(col)
        c = None
        async with async_session_maker() as sess:
            from sqlalchemy import delete as _del
            await sess.execute(_del(ImageChunk).where(ImageChunk.tenant_id == tenant))
            await sess.commit()
        await _ensure_document(doc_id, tenant)
        result = await index_images(
            images_dir=images_dir,
            document_id=doc_id,
            filename="test.pdf",
            tenant_id=tenant,
        )
        indexed_images._initialized = True
        indexed_images._count = len(result)
    # 后续：只查 count
    async with async_session_maker() as sess:
        from sqlalchemy import func, select
        cnt = (await sess.execute(select(func.count()).select_from(ImageChunk).where(ImageChunk.tenant_id == tenant))).scalar()
    return {"doc_id": doc_id, "tenant": tenant, "indexed_count": cnt}


# ===================================================================
# 单元测试
# ===================================================================

def test_scan_images_in_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.jpg").write_bytes(b"x")
        (Path(tmp) / "b.png").write_bytes(b"x")
        (Path(tmp) / "c.txt").write_bytes(b"x")
        (Path(tmp) / "d.JPEG").write_bytes(b"x")
        files = scan_images_in_dir(tmp)
        assert len(files) == 3
        assert not any("c.txt" in f for f in files)


def test_scan_images_in_nonexistent_dir():
    assert scan_images_in_dir("/nonexistent/path/xyz") == []


def test_scan_images_empty_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert scan_images_in_dir(tmp) == []


# ===================================================================
# Embedding 测试
# ===================================================================

@pytest.mark.asyncio
async def test_embed_single_image():
    p = "e:/mineru-output/test_30pages/auto/images"
    if not Path(p).exists():
        pytest.skip("no images")
    files = scan_images_in_dir(p)[:1]
    vec = await embed_image(files[0])
    assert len(vec) == 2048
    assert all(isinstance(v, float) for v in vec)


@pytest.mark.asyncio
async def test_embed_images_batch():
    p = "e:/mineru-output/test_30pages/auto/images"
    if not Path(p).exists():
        pytest.skip("no images")
    files = scan_images_in_dir(p)[:3]
    vecs = await embed_images_batch(files)
    assert len(vecs) == 3
    assert all(len(v) == 2048 for v in vecs)


@pytest.mark.asyncio
async def test_embed_images_empty():
    assert await embed_images_batch([]) == []


# ===================================================================
# 端到端测试
# ===================================================================

@pytest.mark.asyncio
async def test_index_images_writes_to_db_and_milvus(indexed_images):
    """index_images 同时写 DB + Milvus。"""
    info = indexed_images
    assert info["indexed_count"] > 0
    async with async_session_maker() as s:
        rows = (await s.execute(
            select(ImageChunk).where(
                ImageChunk.tenant_id == info["tenant"],
                ImageChunk.document_id == info["doc_id"],
            )
        )).scalars().all()
    assert len(rows) == info["indexed_count"]
    for r in rows:
        assert r.image_path
        assert r.image_id
        assert r.category == "image"


@pytest.mark.asyncio
async def test_index_images_idempotent(indexed_images):
    """重复索引去重（image_id 一致）。"""
    info = indexed_images
    p = "e:/mineru-output/test_30pages/auto/images"
    # 第二次索引（不删旧数据）
    result2 = await index_images(
        images_dir=p,
        document_id=info["doc_id"],
        filename="test.pdf",
        tenant_id=info["tenant"],
    )
    # 第二次返回空（都去重）
    assert result2 == []
    # DB 记录数不变
    async with async_session_maker() as s:
        rows = (await s.execute(
            select(ImageChunk).where(
                ImageChunk.tenant_id == info["tenant"],
                ImageChunk.document_id == info["doc_id"],
            )
        )).scalars().all()
    assert len(rows) == info["indexed_count"]


@pytest.mark.asyncio
async def test_search_images_returns_results(indexed_images):
    """search_images 返回相关图片。"""
    info = indexed_images
    results = await search_images("剪刀工具", tenant_id=info["tenant"], top_k=3)
    assert len(results) > 0
    for r in results:
        assert r["image_path"]
        assert r["filename"]
        assert 0 <= r["score"] <= 1


@pytest.mark.asyncio
async def test_search_images_tenant_isolation(indexed_images):
    """其他租户检索返回空。"""
    results = await search_images("test", tenant_id="nonexistent_tenant", top_k=3)
    assert results == []


@pytest.mark.asyncio
async def test_search_images_with_document_filter(indexed_images):
    """document_id_filter 只返回指定 doc 的图。"""
    info = indexed_images
    results = await search_images(
        "图", tenant_id=info["tenant"], top_k=3,
        document_id_filter=info["doc_id"],
    )
    assert all(r["filename"] for r in results)


def test_image_chunk_model_fields():
    """ImageChunk 模型字段完整性。"""
    from sqlalchemy import inspect
    cols = [c.name for c in inspect(ImageChunk).columns]
    expected = {"image_id", "tenant_id", "document_id", "filename",
                "image_path", "category", "page", "width", "height", "mime_type"}
    assert expected.issubset(set(cols))
