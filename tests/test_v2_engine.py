"""v2_engine: 父块 DB / 子块 Milvus 拆写测试。"""
import os
import asyncio
import pytest

pytest_plugins = ["pytest_asyncio"]


def test_v2_imports():
    from app.rag.v2_engine import (
        index_document, retrieve, RetrievalHit, RetrievalResult,
        get_milvus_store, reset_state,
    )
    assert callable(index_document)
    assert callable(retrieve)


@pytest.mark.asyncio
async def test_get_milvus_store():
    from app.rag.v2_engine import get_milvus_store, reset_state
    reset_state()
    store = await get_milvus_store()
    assert store is not None
    assert store.host == "localhost"
    assert store.port == 19530


@pytest.mark.asyncio
async def test_v2_index_and_retrieve():
    from app.rag.v2_engine import index_document, retrieve, reset_state
    from app.db.session import async_session_maker
    from app.db.models import Document, ParentChunk
    from sqlalchemy import delete
    reset_state()

    async def cleanup():
        async with async_session_maker() as s:
            await s.execute(delete(ParentChunk).where(ParentChunk.document_id == "v2_test_doc"))
            await s.execute(delete(Document).where(Document.document_id == "v2_test_doc"))
            await s.commit()
    await cleanup()

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
    async with async_session_maker() as s2:
        cnt = (await s2.execute(select(func.count()).select_from(ParentChunk).where(ParentChunk.tenant_id=="v2_test_tenant"))).scalar()
        print("  parent_chunks count:", cnt)
    r = await retrieve(
        query="染发前要做什么测试",
        tenant_id="v2_test_tenant",
        top_k=2,
    )
    print("TEST retrieve result:", len(r.hits), "hits", flush=True)
    for i, h in enumerate(r.hits, 1):
        print(f"  Hit{i}: content_len={len(h.content)} content={h.content[:50]!r}", flush=True)
    assert r.tenant_id == "v2_test_tenant"
    assert len(r.hits) > 0, f"应至少 1 个命中，实际 {len(r.hits)}"
    assert all(h.content for h in r.hits), "父块内容应已填充"


@pytest.mark.asyncio
async def test_v2_tenant_isolation():
    from app.rag.v2_engine import index_document, retrieve, reset_state
    from app.db.session import async_session_maker
    from app.db.models import Document, ParentChunk
    from sqlalchemy import delete
    reset_state()

    async def cleanup():
        async with async_session_maker() as s:
            await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id.in_(["iso_A", "iso_B"])))
            await s.execute(delete(Document).where(Document.tenant_id.in_(["iso_A", "iso_B"])))
            await s.commit()
    await cleanup()

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

    r_a = await retrieve(query="染发皮肤测试", tenant_id="iso_A", top_k=3)
    for h in r_a.hits:
        assert h.tenant_id == "iso_A"
        assert h.document_id == "iso_doc_A"
        assert "烫发" not in h.content, f"A 检索不该出现 B 内容: {h.content}"

    r_b = await retrieve(query="烫发软化", tenant_id="iso_B", top_k=3)
    for h in r_b.hits:
        assert h.tenant_id == "iso_B"
        assert h.document_id == "iso_doc_B"
