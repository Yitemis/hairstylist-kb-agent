# -*- coding: utf-8 -*-
"""多租户 + audience 隔离测试 (MASTER_ROADMAP P0-2).

策略:
- 直接用 Milvus client 测 filter (绕过 RAG 层)
- 数据准备: 直接用 mock 嵌入 + Milvus insert
- 验证 filter 表达式真的工作
"""
import asyncio
import pytest
import hashlib
import math
from unittest.mock import patch

from app.db.models import Document, ParentChunk
from app.db.session import async_session_maker
from sqlalchemy import delete, select


# ===================================================================
# 1. Milvus 直接 filter 测试 (最稳)
# ===================================================================

@pytest.fixture
async def clean_milvus_and_pg():
    """每个测试前清空。"""
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    for col in c.list_collections():
        c.drop_collection(col)
    c = None
    async with async_session_maker() as s:
        await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id.in_(["mt_a", "mt_b", "mt_c"])))
        await s.execute(delete(Document).where(Document.tenant_id.in_(["mt_a", "mt_b", "mt_c"])))
        await s.commit()
    yield


def _mock_vector():
    """返回 dim 维 mock 向量 - dim 自动从 Milvus 集合读 (不写死)。"""
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    if "hairstylist_kb" not in c.list_collections():
        return [0.5] * 1024  # 集合还没创建时的 fallback
    s = c.describe_collection("hairstylist_kb")
    dim = next((f["params"]["dim"] for f in s["fields"] if f.get("params", {}).get("dim")), 1024)
    v = [0.5] * dim
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


async def _ensure_doc(doc_id: str, tenant_id: str, audience: str = "user", category: str = "haircare"):
    """确保 PG 中 doc 存在。"""
    async with async_session_maker() as s:
        existing = (await s.execute(select(Document).where(Document.document_id == doc_id))).scalar_one_or_none()
        if existing:
            return
        s.add(Document(
            document_id=doc_id, tenant_id=tenant_id,
            filename=f"{doc_id}.pdf", category=category, audience=audience,
        ))
        await s.commit()


async def _insert_via_milvus(doc_id: str, tenant_id: str, audience: str, category: str):
    """用 mock 向量直接 insert 到 Milvus。"""
    from app.rag.milvus_store import MilvusStore
    ms = MilvusStore()  # default config
    ms.ensure_collection()
    vec = _mock_vector()
    payload = {
        "parent_id": f"parent_{doc_id}",
        "tenant_id": tenant_id,
        "document_id": doc_id,
        "filename": f"{doc_id}.pdf",
        "category": category,
        "audience": audience,
    }
    ms.insert([vec], [payload])


async def _setup_test_data():
    """建 3 个 doc (同 tenant 不同 audience + 不同 tenant 同 audience)。"""
    # 全部用 audience=user
    await _ensure_doc("mt_a_user_doc", "mt_a", audience="user")
    await _ensure_doc("mt_a_staff_doc", "mt_a", audience="staff")
    await _ensure_doc("mt_a_all_doc", "mt_a", audience="all")
    # 另一个 tenant 同 audience
    await _ensure_doc("mt_b_user_doc", "mt_b", audience="user")
    # Insert to Milvus
    for d in [("mt_a_user_doc", "mt_a", "user", "haircare"),
              ("mt_a_staff_doc", "mt_a", "staff", "haircare"),
              ("mt_a_all_doc", "mt_a", "all", "haircare"),
              ("mt_b_user_doc", "mt_b", "user", "haircare")]:
        await _insert_via_milvus(*d)
    # Milvus read consistency delay
    import asyncio as _aio
    await _aio.sleep(2)


# ===================================================================
# 测试用例
# ===================================================================

@pytest.mark.asyncio
async def test_tenant_filter_isolates(clean_milvus_and_pg):
    """tenant_id filter 严格隔离: mt_a 看不到 mt_b 的 doc。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb", filter='tenant_id == "mt_a"',
                   output_fields=["document_id"], limit=20)
    doc_ids = {r["document_id"] for r in rows}
    # mt_a 应有 3 个 doc (user + staff + all)
    assert "mt_a_user_doc" in doc_ids
    assert "mt_a_staff_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    # mt_b 不应看到
    assert "mt_b_user_doc" not in doc_ids, f"Cross-tenant leak: {doc_ids}"


@pytest.mark.asyncio
async def test_audience_user_filter(clean_milvus_and_pg):
    """audience=user filter 只看到 user + all 文档。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb", filter='tenant_id == "mt_a" and audience in ["user", "all"]',
                   output_fields=["document_id", "audience"], limit=20)
    doc_ids = {r["document_id"] for r in rows}
    # user + all 文档
    assert "mt_a_user_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    # 不应看到 staff
    assert "mt_a_staff_doc" not in doc_ids, f"User leaks staff: {doc_ids}"


@pytest.mark.asyncio
async def test_audience_staff_filter(clean_milvus_and_pg):
    """audience=staff filter 只看到 staff + all 文档。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb", filter='tenant_id == "mt_a" and audience in ["staff", "all"]',
                   output_fields=["document_id", "audience"], limit=20)
    doc_ids = {r["document_id"] for r in rows}
    assert "mt_a_staff_doc" in doc_ids
    assert "mt_a_all_doc" in doc_ids
    assert "mt_a_user_doc" not in doc_ids, f"Staff leaks user: {doc_ids}"


@pytest.mark.asyncio
async def test_combined_tenant_and_audience(clean_milvus_and_pg):
    """组合 filter: tenant=mt_a + audience=staff 应只看到 mt_a_staff_doc。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb",
                   filter='tenant_id == "mt_a" and audience == "staff"',
                   output_fields=["document_id"], limit=20)
    doc_ids = {r["document_id"] for r in rows}
    assert doc_ids == {"mt_a_staff_doc"}, doc_ids


@pytest.mark.asyncio
async def test_milvus_payload_contains_required_fields(clean_milvus_and_pg):
    """Milvus payload 必须有 tenant_id / document_id / audience / category 字段。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb", filter='', output_fields=[
        "id", "tenant_id", "document_id", "filename", "audience", "category"
    ], limit=20)
    assert len(rows) >= 4
    by_doc = {r["document_id"]: r for r in rows}
    assert by_doc["mt_a_user_doc"]["tenant_id"] == "mt_a"
    assert by_doc["mt_a_user_doc"]["audience"] == "user"
    assert by_doc["mt_a_staff_doc"]["audience"] == "staff"
    assert by_doc["mt_a_all_doc"]["audience"] == "all"
    assert by_doc["mt_b_user_doc"]["tenant_id"] == "mt_b"


@pytest.mark.asyncio
async def test_no_tenant_returns_empty(clean_milvus_and_pg):
    """不存在的 tenant 返回空 (无 cross-tenant 泄露)。"""
    await _setup_test_data()
    from pymilvus import MilvusClient
    c = MilvusClient(uri="http://localhost:19530")
    rows = c.query("hairstylist_kb", filter='tenant_id == "nonexistent"',
                   output_fields=["document_id"], limit=20)
    assert len(rows) == 0
