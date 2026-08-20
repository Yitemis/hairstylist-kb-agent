# -*- coding: utf-8 -*-
"""多租户 + audience 隔离测试 (MASTER_ROADMAP P0-2).

P2-基础设施: 改用 PgvectorStore (替代 MilvusClient 底层调用).
策略:
- 直接用 PgvectorStore 测 filter (绕过 RAG 层)
- 数据准备: 直接用 mock 嵌入 + pgvector insert
- 验证 filter 表达式真的工作
"""
import asyncio
import math
import uuid

import pytest
import hashlib

from app.db.models import Document, ParentChunk
from app.db.session import async_session_maker
from sqlalchemy import delete, select


# ============================================================
# 1. pgvector 直接 filter 测试 (替代 MilvusClient)
# ============================================================

@pytest.fixture
async def clean_pgvector_and_pg():
    """每个测试前清空."""
    from app.db.session import async_session_maker
    from sqlalchemy import text

    async with async_session_maker() as s:
        await s.execute(text("TRUNCATE TABLE child_chunks"))
        await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id.in_(["mt_a", "mt_b", "mt_c"])))
        await s.execute(delete(Document).where(Document.tenant_id.in_(["mt_a", "mt_b", "mt_c"])))
        await s.commit()
    yield


def _mock_vector(dim: int = 1024) -> list:
    """返回 dim 维 mock 向量 (归一化)."""
    v = [0.5] * dim
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


async def _ensure_doc(doc_id: str, tenant_id: str, audience: str = "user", category: str = "haircare"):
    """确保 PG 中 doc 存在."""
    async with async_session_maker() as s:
        existing = (await s.execute(select(Document).where(Document.document_id == doc_id))).scalar_one_or_none()
        if existing:
            return
        s.add(Document(
            document_id=doc_id, tenant_id=tenant_id,
            filename=f"{doc_id}.pdf", category=category, audience=audience,
        ))
        await s.commit()


async def _insert_via_pgvector(doc_id: str, tenant_id: str, audience: str, category: str):
    """用 mock 向量直接 insert 到 pgvector."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    vec = _mock_vector()
    payload = {
        "parent_id": f"parent_{doc_id}",
        "tenant_id": tenant_id,
        "document_id": doc_id,
        "filename": f"{doc_id}.pdf",
        "category": category,
        "audience": audience,
    }
    await store.insert([vec], [payload])


async def _setup_test_data():
    """建 3 个 doc (同 tenant 不同 audience + 不同 tenant 同 audience)."""
    await _ensure_doc("mt_a_user_doc", "mt_a", audience="user")
    await _ensure_doc("mt_a_staff_doc", "mt_a", audience="staff")
    await _ensure_doc("mt_a_all_doc", "mt_a", audience="all")
    await _ensure_doc("mt_b_user_doc", "mt_b", audience="user")
    for d in [("mt_a_user_doc", "mt_a", "user", "haircare"),
              ("mt_a_staff_doc", "mt_a", "staff", "haircare"),
              ("mt_a_all_doc", "mt_a", "all", "haircare"),
              ("mt_b_user_doc", "mt_b", "user", "haircare")]:
        await _insert_via_pgvector(*d)


# ============================================================
# 测试用例
# ============================================================

@pytest.mark.asyncio
async def test_tenant_filter_isolates(clean_pgvector_and_pg):
    """tenant_id filter 严格隔离: mt_a 看不到 mt_b 的 doc."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="mt_a", top_k=20,
    )
    doc_ids = {r["document_id"] for r in results}
    assert "mt_a_user_doc" in doc_ids
    assert "mt_a_staff_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    assert "mt_b_user_doc" not in doc_ids, f"Cross-tenant leak: {doc_ids}"


@pytest.mark.asyncio
async def test_audience_user_filter(clean_pgvector_and_pg):
    """audience=user filter 只看到 user + all 文档."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="mt_a", top_k=20,
        audience_filter=["user", "all"],
    )
    doc_ids = {r["document_id"] for r in results}
    assert "mt_a_user_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    assert "mt_a_staff_doc" not in doc_ids, f"User leaks staff: {doc_ids}"


@pytest.mark.asyncio
async def test_audience_staff_filter(clean_pgvector_and_pg):
    """audience=staff filter 只看到 staff + all 文档."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="mt_a", top_k=20,
        audience_filter=["staff", "all"],
    )
    doc_ids = {r["document_id"] for r in results}
    assert "mt_a_staff_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    assert "mt_a_user_doc" not in doc_ids, f"Staff leaks user: {doc_ids}"


@pytest.mark.asyncio
async def test_combined_tenant_and_audience(clean_pgvector_and_pg):
    """组合 filter: tenant=mt_a + audience=staff 应只看到 mt_a_staff_doc."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="mt_a", top_k=20,
        audience_filter=["staff"],
    )
    doc_ids = {r["document_id"] for r in results}
    assert doc_ids == {"mt_a_staff_doc"}, doc_ids


@pytest.mark.asyncio
async def test_pgvector_payload_contains_required_fields(clean_pgvector_and_pg):
    """pgvector 字段必须有 tenant_id / document_id / audience / category 字段."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="mt_a", top_k=20,
    )
    by_doc = {r["document_id"]: r for r in results}
    assert len(by_doc) >= 3
    assert by_doc["mt_a_user_doc"]["tenant_id"] == "mt_a"
    assert by_doc["mt_a_user_doc"]["audience"] == "user"
    assert by_doc["mt_a_staff_doc"]["audience"] == "staff"
    assert by_doc["mt_a_all_doc"]["audience"] == "all"


@pytest.mark.asyncio
async def test_no_tenant_returns_empty(clean_pgvector_and_pg):
    """不存在的 tenant 返回空 (无 cross-tenant 泄露)."""
    await _setup_test_data()
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore()
    results = await store.search(
        _mock_vector(), tenant_id="nonexistent", top_k=20,
    )
    assert len(results) == 0
