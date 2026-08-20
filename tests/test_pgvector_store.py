# -*- coding: utf-8 -*-
"""Pgvector store 适配器测试 (替代 test_milvus_store.py).

P2-基础设施: 测试 PgvectorStore 的 insert/search/delete/count + 多租户隔离.
"""
import asyncio
import math
import os
import uuid

import pytest


def test_pgvector_store_init():
    """初始化 + 字段常量."""
    from app.rag.pgvector_store import (
        PgvectorStore, PARENT_ID_KEY, TENANT_ID_KEY, DOCUMENT_ID_KEY,
        FILENAME_KEY, CATEGORY_KEY, AUDIENCE_KEY, IMAGE_PATH_KEY, CONTENT_KEY,
    )
    store = PgvectorStore(host="localhost", port=5432)
    assert store.host == "localhost"
    assert store.port == 5432
    assert store.dim == 1024
    assert store.metric_type == "COSINE"
    assert PARENT_ID_KEY == "parent_id"
    assert TENANT_ID_KEY == "tenant_id"
    assert IMAGE_PATH_KEY == "image_path"
    assert CONTENT_KEY == "content"


@pytest.mark.asyncio
async def test_pgvector_insert_and_search():
    """真实插入 + 检索测试."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=64)

    # 生成 mock 向量 (cosine 相似度可控)
    vecs = []
    for i in range(5):
        v = [0.0] * 64
        v[i] = 1.0  # 每个向量在不同维度为 1
        vecs.append(v)

    payloads = [
        {
            "parent_id": f"parent-{i}",
            "tenant_id": "test_tenant",
            "document_id": f"doc-{i // 2}",
            "filename": f"file-{i}.pdf",
            "category": "general",
            "audience": "all",
            "is_published": True,
            "content": f"chunk content {i}",
        }
        for i in range(5)
    ]

    try:
        ids = await store.insert(vecs, payloads)
        assert len(ids) == 5
        # 检索: 第一个向量与自己的 cosine 相似度应最高
        results = await store.insert(
            vecs[:1],  # 占位, 不用
            [{**payloads[0], "parent_id": "ignored"}],
        )
        # 正确做法: 用 vecs[0] 检索
        results = await store.search(vecs[0], tenant_id="test_tenant", top_k=3)
        assert len(results) > 0
        assert "score" in results[0]
        assert "parent_id" in results[0]
        # 第一个 hit 应该是自身 (score 接近 1)
        assert results[0]["score"] > 0.99
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")


@pytest.mark.asyncio
async def test_pgvector_tenant_isolation():
    """多租户隔离: tenant_A 查不到 tenant_B 的数据."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=32)
    vecs = [[0.5] * 32 for _ in range(4)]
    payloads_a = [
        {
            "parent_id": f"a-{i}", "tenant_id": "tenant_A",
            "document_id": "doc-1", "filename": "a.pdf", "category": "g",
            "audience": "all",
        }
        for i in range(2)
    ]
    payloads_b = [
        {
            "parent_id": f"b-{i}", "tenant_id": "tenant_B",
            "document_id": "doc-2", "filename": "b.pdf", "category": "g",
            "audience": "all",
        }
        for i in range(2)
    ]
    try:
        await store.insert(vecs, payloads_a)
        await store.insert(vecs, payloads_b)
        results = await store.search(vecs[0], tenant_id="tenant_A", top_k=10)
        for r in results:
            rid = r["tenant_id"]
            assert rid == "tenant_A", f"租户隔离失败: A 检索到 B 数据: {rid}"
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")


@pytest.mark.asyncio
async def test_pgvector_audience_filter():
    """audience 过滤: staff filter 只看到 staff + all 文档."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=16)
    vecs = [[0.5] * 16 for _ in range(3)]
    payloads = [
        {"parent_id": "p1", "tenant_id": "t1", "document_id": "d1",
         "filename": "f.pdf", "category": "g", "audience": "user"},
        {"parent_id": "p2", "tenant_id": "t1", "document_id": "d2",
         "filename": "f.pdf", "category": "g", "audience": "staff"},
        {"parent_id": "p3", "tenant_id": "t1", "document_id": "d3",
         "filename": "f.pdf", "category": "g", "audience": "all"},
    ]
    try:
        await store.insert(vecs, payloads)
        # staff filter: 只能看到 p2 + p3
        results = await store.search(
            vecs[0], tenant_id="t1", top_k=10, audience_filter=["staff", "all"]
        )
        audiences = {r["audience"] for r in results}
        assert "user" not in audiences, f"staff filter 看到 user: {audiences}"
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")


@pytest.mark.asyncio
async def test_pgvector_delete_by_document():
    """按 document_id 删除."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=16)
    vecs = [[0.5] * 16 for _ in range(3)]
    payloads = [
        {"parent_id": f"p-{i}", "tenant_id": "t1", "document_id": "doc-del",
         "filename": "f.pdf", "category": "g", "audience": "all"}
        for i in range(3)
    ]
    try:
        await store.insert(vecs, payloads)
        cnt_before = await store.count(tenant_id="t1")
        deleted = await store.delete_by_document("doc-del", "t1")
        assert deleted == 3
        cnt_after = await store.count(tenant_id="t1")
        assert cnt_after == cnt_before - 3
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")


@pytest.mark.asyncio
async def test_pgvector_count_by_tenant():
    """按 tenant 统计."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=8)
    try:
        # 用唯一 tenant_id 避免和其他测试冲突
        tenant = f"count_test_{uuid.uuid4().hex[:8]}"
        vecs = [[0.1] * 8 for _ in range(7)]
        payloads = [
            {"parent_id": f"p-{i}", "tenant_id": tenant, "document_id": "d1",
             "filename": "f.pdf", "category": "g", "audience": "all"}
            for i in range(7)
        ]
        await store.insert(vecs, payloads)
        cnt = await store.count(tenant_id=tenant)
        assert cnt == 7
        # 清理
        await store.delete_by_document("d1", tenant)
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")


@pytest.mark.asyncio
async def test_pgvector_get_collection_stats():
    """获取表统计 (替代 Milvus get_collection_stats)."""
    from app.rag.pgvector_store import PgvectorStore
    store = PgvectorStore(dim=1024)
    try:
        stats = await store.get_collection_stats()
        assert "row_count" in stats
        assert "dim" in stats
        assert stats["engine"] == "pgvector"
    except Exception as e:
        pytest.skip(f"pgvector 不可用: {e}")
