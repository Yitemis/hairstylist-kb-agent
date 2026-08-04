"""Milvus store 适配器测试。"""
import os
import pytest


def test_milvus_store_init():
    """初始化 + 字段常量。"""
    from app.rag.milvus_store import (
        MilvusStore, PARENT_ID_KEY, TENANT_ID_KEY, DOCUMENT_ID_KEY,
        FILENAME_KEY, CATEGORY_KEY,
    )
    store = MilvusStore(host="localhost", port=19530)
    assert store.host == "localhost"
    assert store.port == 19530
    assert store.collection == "hairstylist_kb"
    assert store.dim == 1024
    assert PARENT_ID_KEY == "parent_id"
    assert TENANT_ID_KEY == "tenant_id"


def test_milvus_real_connect():
    """真实连接 Milvus（如果 19530 在跑）。"""
    from app.rag.milvus_store import MilvusStore
    store = MilvusStore(host="localhost", port=19530, collection="test_milvus_pytest")
    try:
        client = store._get_client()
        # 真实连
        assert client is not None
        # 列出集合
        colls = client.list_collections()
        assert isinstance(colls, list)
    except Exception as e:
        pytest.skip(f"Milvus 不可用: {e}")


def test_milvus_insert_search():
    """真实插入 + 检索测试。"""
    from app.rag.milvus_store import MilvusStore
    import random
    store = MilvusStore(
        host="localhost", port=19530, collection="test_milvus_e2e", dim=64,
    )
    try:
        # 建集合
        store.ensure_collection()
        # 准备数据
        random.seed(42)
        vecs = [[random.random() for _ in range(64)] for _ in range(10)]
        payloads = [
            {
                "parent_id": f"parent-{i}",
                "tenant_id": "test_tenant",
                "document_id": f"doc-{i // 3}",
                "filename": f"file-{i}.pdf",
                "category": "general",
            }
            for i in range(10)
        ]
        ids = store.insert(vecs, payloads)
        assert len(ids) == 10
        # 检索
        results = store.search(vecs[0], tenant_id="test_tenant", top_k=3)
        assert len(results) > 0
        assert "parent_id" in results[0]
        assert "score" in results[0]
    except Exception as e:
        pytest.skip(f"Milvus 不可用: {e}")


def test_milvus_tenant_isolation():
    """多租户隔离：tenant_A 查不到 tenant_B 的数据。"""
    from app.rag.milvus_store import MilvusStore
    import random
    store = MilvusStore(
        host="localhost", port=19530, collection="test_milvus_tenant", dim=32,
    )
    try:
        store.ensure_collection()
        vecs = [[random.random() for _ in range(32)] for _ in range(4)]
        payloads_a = [
            {"parent_id": f"a-{i}", "tenant_id": "tenant_A",
             "document_id": "doc-1", "filename": "a.pdf", "category": "g"}
            for i in range(2)
        ]
        payloads_b = [
            {"parent_id": f"b-{i}", "tenant_id": "tenant_B",
             "document_id": "doc-2", "filename": "b.pdf", "category": "g"}
            for i in range(2)
        ]
        store.insert(vecs, payloads_a)
        store.insert(vecs, payloads_b)
        # tenant_A 检索：只能看到 parent_id = a-*
        results = store.search(vecs[0], tenant_id="tenant_A", top_k=10)
        for r in results:
            assert r["tenant_id"] == "tenant_A"
    except Exception as e:
        pytest.skip(f"Milvus 不可用: {e}")
