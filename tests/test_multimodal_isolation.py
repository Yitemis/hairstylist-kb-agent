# -*- coding: utf-8 -*-
"""多模态 + role 隔离测试 (mock embedding 避免 403).

P2-基础设施: 改用 pgvector (替代 MilvusClient 底层调用).
"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch

# Mock embedding function (避免 火山方舟 403)
async def mock_get_embedding(texts):
    import hashlib
    vecs = []
    for t in texts:
        h = hashlib.md5(t.encode()).hexdigest()
        v = []
        for i in range(0, len(h) * 2, 2):
            v.append(float(int(h[i % len(h):(i % len(h)) + 2], 16)) / 255)
        # Pad to 1024 (BGE dim, pgvector 用这个)
        while len(v) < 1024:
            v.extend(v[:min(len(v), 1024 - len(v))])
        v = v[:1024]
        vecs.append(v)
    return vecs


# 替换 _get_embedding
from app.rag import v2_engine

async def _patched_get_embedding(texts):
    return await mock_get_embedding(texts)

# 单元测试
def test_audience_for_user_vs_staff():
    from app.rag.multimodal_chat import get_audience_for_user
    assert get_audience_for_user(is_staff=False) == "user"
    assert get_audience_for_user(is_staff=True) == "staff"


def test_system_prompt_differs_by_role():
    from app.rag.multimodal_chat import get_system_prompt
    p_user = get_system_prompt(is_staff=False)
    p_staff = get_system_prompt(is_staff=True)
    assert p_user != p_staff
    assert "C 端" in p_user
    assert "商家" in p_staff or "员工" in p_staff


def test_build_image_blocks():
    from app.rag.multimodal_chat import build_image_blocks
    assert build_image_blocks([], []) == []
    blocks = build_image_blocks([], ["data:image/jpeg;base64,abc"])
    assert len(blocks) == 1


def test_build_multimodal_messages_text_only():
    from app.rag.multimodal_chat import build_multimodal_messages
    msgs = build_multimodal_messages(text="hello", system_prompt="sys")
    assert len(msgs) == 2
    assert msgs[1]["content"] == [{"type": "text", "text": "hello"}]


def test_build_multimodal_messages_with_knowledge():
    from app.rag.multimodal_chat import build_multimodal_messages
    msgs = build_multimodal_messages(text="q", knowledge_context="ctx")
    assert "知识库参考" in msgs[0]["content"]


# 集成测试 - 用 mock embedding
async def _cleanup(tenant, doc_ids):
    from app.db.models import ParentChunk
    from app.db.session import async_session_maker
    from sqlalchemy import delete, text
    async with async_session_maker() as s:
        # 清理 child_chunks (P2-基础设施, 替代 Milvus drop)
        await s.execute(text("TRUNCATE TABLE child_chunks"))
        for did in doc_ids:
            await s.execute(delete(ParentChunk).where(ParentChunk.document_id == did))
            await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id == tenant))
            from app.db.models import Document
            await s.execute(delete(Document).where(Document.document_id == did))
        await s.commit()


@pytest.fixture(autouse=True)
def mock_embedding():
    """替换 _get_embedding 为 mock."""
    with patch.object(v2_engine, '_get_embedding', _patched_get_embedding):
        yield


@pytest.fixture
async def isolated_kb():
    """建 3 个文档: user / staff / all."""
    v2_engine.reset_state()
    tenant = "isolation_test"
    docs = ["user_doc_iso", "staff_doc_iso", "all_doc_iso"]
    await _cleanup(tenant, docs)
    await v2_engine.index_document(
        document_id="user_doc_iso",
        content="用户专属发型知识: 圆脸适合短发刘海, 避免厚重感.",
        filename="user.pdf", tenant_id=tenant, category="haircare", audience="user",
    )
    await v2_engine.index_document(
        document_id="staff_doc_iso",
        content="商家操作指南: 圆脸剪发技术细节, 鬓角推剪 45 度.",
        filename="staff.pdf", tenant_id=tenant, category="haircare", audience="staff",
    )
    await v2_engine.index_document(
        document_id="all_doc_iso",
        content="通用科普: 理发基础.",
        filename="all.pdf", tenant_id=tenant, category="haircare", audience="all",
    )
    yield {"tenant": tenant, "docs": docs}
    await _cleanup(tenant, docs)


@pytest.mark.asyncio
async def test_user_only_sees_user_and_all(isolated_kb):
    """C 端用户: 只看 user + all 文档."""
    info = isolated_kb
    r = await v2_engine.retrieve(
        query="圆脸", tenant_id=info["tenant"], top_k=10,
        audience_filter=["user", "all"],
    )
    doc_ids = {h.document_id for h in r.hits}
    assert "user_doc_iso" in doc_ids
    assert "all_doc_iso" in doc_ids
    assert "staff_doc_iso" not in doc_ids


@pytest.mark.asyncio
async def test_staff_only_sees_staff_and_all(isolated_kb):
    """商家: 只看 staff + all 文档."""
    info = isolated_kb
    r = await v2_engine.retrieve(
        query="圆脸", tenant_id=info["tenant"], top_k=10,
        audience_filter=["staff", "all"],
    )
    doc_ids = {h.document_id for h in r.hits}
    assert "staff_doc_iso" in doc_ids
    assert "all_doc_iso" in doc_ids
    assert "user_doc_iso" not in doc_ids


@pytest.mark.asyncio
async def test_audience_all_returns_everything(isolated_kb):
    """audience_filter=None 不过滤."""
    info = isolated_kb
    r = await v2_engine.retrieve(
        query="圆脸", tenant_id=info["tenant"], top_k=10,
    )
    doc_ids = {h.document_id for h in r.hits}
    assert len(doc_ids & set(info["docs"])) == 3


@pytest.mark.asyncio
async def test_index_document_persists_audience(isolated_kb):
    """index_document 把 audience 存到 Document.audience."""
    from app.db.models import Document
    from app.db.session import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as s:
        doc = (await s.execute(select(Document).where(Document.document_id == "user_doc_iso"))).scalar_one()
    assert doc.audience == "user"
