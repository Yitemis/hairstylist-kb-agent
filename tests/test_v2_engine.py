"""v2_engine: 父块 DB / 子块 pgvector 拆写测试 (P2-基础设施, 替代 Milvus)."""
import os
import asyncio
import pytest

pytest_plugins = ["pytest_asyncio"]


def test_v2_imports():
    from app.rag.v2_engine import (
        index_document, retrieve, RetrievalHit, RetrievalResult,
        get_vector_store, get_milvus_store, reset_state,  # 向后兼容
    )
    assert callable(index_document)
    assert callable(retrieve)
    assert callable(get_vector_store)


@pytest.mark.asyncio
async def test_get_vector_store():
    """P2-基础设施: get_vector_store 返回 PgvectorStore (默认)."""
    from app.rag.v2_engine import get_vector_store, reset_state
    reset_state()
    store = await get_vector_store()
    assert store is not None
    # P2: 默认应该是 PgvectorStore
    from app.rag.pgvector_store import PgvectorStore
    assert isinstance(store, PgvectorStore)


async def _cleanup_v2_test(tenant_ids=None, document_ids=None):
    """统一清理: parent + child + document 全部删, 避免 pgvector 孤儿数据."""
    from sqlalchemy import delete
    from app.db.session import async_session_maker
    from app.db.models import Document, ParentChunk, ChildChunk
    async with async_session_maker() as s:
        if document_ids:
            await s.execute(delete(ChildChunk).where(ChildChunk.document_id.in_(document_ids)))
            await s.execute(delete(ParentChunk).where(ParentChunk.document_id.in_(document_ids)))
            await s.execute(delete(Document).where(Document.document_id.in_(document_ids)))
        if tenant_ids:
            await s.execute(delete(ChildChunk).where(ChildChunk.tenant_id.in_(tenant_ids)))
            await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id.in_(tenant_ids)))
            await s.execute(delete(Document).where(Document.tenant_id.in_(tenant_ids)))
        await s.commit()


@pytest.mark.asyncio
async def test_v2_index_and_retrieve():
    from app.rag.v2_engine import index_document, retrieve, reset_state
    reset_state()

    # 清理 (含 child_chunks, 避免 pgvector 孤儿)
    await _cleanup_v2_test(
        tenant_ids=["v2_test_tenant"], document_ids=["v2_test_doc"],
    )

    content = """# 第一章 头发护理基础

## 洗发
洗发时水温控制在 38-40 度，避免过高伤害头皮。

## 护发
护发素停留 3-5 分钟再冲洗。

# 第二章 染发技术

## 染前测试
染前 48 小时做皮肤测试。

## 上色时间
根据颜色深度上色 20-40 分钟。
"""

    result = await index_document(
        document_id="v2_test_doc",
        content=content,
        filename="test.pdf",
        tenant_id="v2_test_tenant",
        category="haircare",
    )
    assert result["status"] == "ok"
    assert result["parents"] > 0
    assert result["children"] > 0

    print("TEST: Before retrieve, parents in DB:")
    from sqlalchemy import select, func
    from app.db.session import async_session_maker
    from app.db.models import ParentChunk
    async with async_session_maker() as s2:
        cnt = (await s2.execute(select(func.count()).select_from(ParentChunk).where(ParentChunk.tenant_id=="v2_test_tenant"))).scalar()
        print("  parent_chunks count:", cnt)
    # Fix: index_document 默认 is_published=False, 测试要传 include_unpublished=True
    r = await retrieve(
        query="染发前要做什么测试",
        tenant_id="v2_test_tenant",
        top_k=2,
        include_unpublished=True,
    )
    print("TEST retrieve result:", len(r.hits), "hits", flush=True)
    for i, h in enumerate(r.hits, 1):
        print(f"  Hit{i}: content_len={len(h.content)} content={h.content[:50]!r}", flush=True)
    assert r.tenant_id == "v2_test_tenant"
    assert len(r.hits) > 0, f"应至少 1 个命中，实际 {len(r.hits)}"
    assert all(h.content for h in r.hits), "父块内容应已填充"

    # 清理
    await _cleanup_v2_test(
        tenant_ids=["v2_test_tenant"], document_ids=["v2_test_doc"],
    )


@pytest.mark.asyncio
async def test_v2_tenant_isolation():
    from app.rag.v2_engine import index_document, retrieve, reset_state
    reset_state()

    # 清理
    await _cleanup_v2_test(tenant_ids=["iso_A", "iso_B"])

    await index_document(
        document_id="iso_doc_A",
        content="# 染发\n染发需要做皮肤测试",
        filename="a.pdf",
        tenant_id="iso_A",
    )
    await index_document(
        document_id="iso_doc_B",
        content="# 烫发\n烫发前要软化头发",
        filename="b.pdf",
        tenant_id="iso_B",
    )

    # Fix: 测试数据 is_published=False, 加 include_unpublished=True
    r_a = await retrieve(
        query="染发皮肤测试", tenant_id="iso_A", top_k=3,
        include_unpublished=True,
    )
    for h in r_a.hits:
        assert h.tenant_id == "iso_A"
        assert h.document_id == "iso_doc_A"
        assert "烫发" not in h.content, f"A 检索不该出现 B 内容: {h.content}"

    r_b = await retrieve(
        query="烫发软化", tenant_id="iso_B", top_k=3,
        include_unpublished=True,
    )
    for h in r_b.hits:
        assert h.tenant_id == "iso_B"
        assert h.document_id == "iso_doc_B"

    # 清理
    await _cleanup_v2_test(tenant_ids=["iso_A", "iso_B"])
