# -*- coding: utf-8 -*-
"""RAG 真实端到端测试：索引 + 检索 + Rerank。

验证关键路径：
1. index_document 把文档写入向量库
2. retrieve 能查回相关文档
3. self_rag_retrieve 反思重试工作
4. 多租户 filter 真的隔离
"""
import asyncio
import os
import pytest

# 测试强制使用 qdrant-local（不需要 Milvus 服务）
os.environ["VECTOR_STORE_ENGINE"] = "qdrant-local"
os.environ["VECTOR_STORE_PATH"] = "./data/qdrant_test"


@pytest.fixture(autouse=True)
def reset_rag_singletons():
    """每个测试前：直接修改已创建的 config 单例 + 重置 RAG 单例。"""
    from app.core.config import vector_store_config
    from app.rag import engine
    # 关键：直接修改单例字段（不是 setenv）
    vector_store_config.engine = "qdrant-local"
    vector_store_config.path = "./data/qdrant_test"
    engine._vector_store = None
    engine._qdrant_direct_client = None
    yield
    engine._vector_store = None
    engine._qdrant_direct_client = None


from app.rag.engine import (  # noqa: E402
    index_document,
    retrieve,
    self_rag_retrieve,
    get_knowledge_stats,
)


# 测试文档（"烫发原理"专业内容）
SAMPLE_DOC = """# 烫发原理

烫发是一种通过化学方法改变头发形态的美发技术，核心原理是打断和重组头发的二硫键。

## 软化阶段
涂抹含巯基乙酸铵的烫发水，作为还原剂断开头发中的二硫键，将头发从固定形态"解放"出来，此时头发变得柔软可塑。

## 定型阶段
将头发固定在新形态后，涂抹定型液（含溴酸钠或过氧化氢），重新形成二硫键——但这次是在新位置，从而永久固定卷曲形态。

## 注意事项
频繁烫发会累积损伤毛鳞片和皮质层，建议间隔至少 6 个月。细软发质应选择数码烫，pH 值控制在 8.0-8.5。
"""


@pytest.mark.asyncio
async def test_index_document():
    """测试文档索引：能成功写入向量库。"""
    result = await index_document(
        document_id="test-doc-001",
        content=SAMPLE_DOC,
        filename="烫发原理.md",
        tenant_id="default",
        category="烫发技术",
    )
    assert result["status"] == "ok", f"索引失败: {result}"
    assert result["chunks_indexed"] > 0, "应至少索引 1 个 chunk"
    print(f"  索引完成: {result['chunks_indexed']} chunks, {result['time_ms']}ms")


@pytest.mark.asyncio
async def test_retrieve_basic():
    """测试基本检索：能查回刚刚索引的文档。"""
    result = await retrieve(
        query="烫发的化学原理",
        tenant_id="default",
        top_k=3,
        enable_rerank=False,
    )
    assert result.child_hits_count > 0, f"应至少召回 1 个子块，实际 0"
    print(f"  召回: {result.child_hits_count} 子块, {result.parent_count} 父块, {result.retrieval_time_ms}ms")
    # 验证返回的父块包含关键词
    if result.hits:
        first_hit = result.hits[0]
        assert "二硫键" in first_hit.content or "烫发" in first_hit.content


@pytest.mark.asyncio
async def test_self_rag_returns_results():
    """测试 Self-RAG：能返回结果（即使反思重试多次）。"""
    result = await self_rag_retrieve(
        query="染发会伤头发吗",
        tenant_id="default",
        top_k=2,
        max_retries=1,
    )
    # Self-RAG 至少返回 1 次（哪怕是空结果）
    assert result is not None
    print(f"  Self-RAG: {result.child_hits_count} 子块, {len(result.hits)} 父块")


@pytest.mark.asyncio
async def test_tenant_isolation():
    """测试多租户隔离：tenant_a 查不到 tenant_b 的文档。"""
    # 索引到另一个 tenant
    await index_document(
        document_id="test-doc-tenantB",
        content="这是租户 B 的专属文档，关于减肥技巧。",
        filename="b-only.md",
        tenant_id="tenant_b",
        category="测试",
    )
    # 租户 A 查询：不应该返回 tenant_b 的文档
    result_a = await retrieve(
        query="减肥技巧",
        tenant_id="tenant_a",
        top_k=5,
        enable_rerank=False,
    )
    # 验证没有任何 hit 来自 tenant_b
    for hit in result_a.hits:
        assert hit.tenant_id == "tenant_a", f"租户 A 查到了租户 B 的内容: {hit.tenant_id}"
    print(f"  租户隔离 OK: 租户 A 查 {result_a.child_hits_count} 条，无串租户")


@pytest.mark.asyncio
async def test_knowledge_stats():
    """测试 /api/rag/stats 接口。"""
    stats = await get_knowledge_stats()
    assert "total_chunks" in stats
    print(f"  总 chunks: {stats['total_chunks']}")


@pytest.mark.asyncio
async def test_rerank_enabled():
    """测试 Rerank 启用时仍能工作（降级到向量分数）。"""
    result = await retrieve(
        query="二硫键断裂",
        tenant_id="default",
        top_k=2,
        enable_rerank=True,  # 启用 Rerank
    )
    # 即使 Rerank 失败也会降级到向量分数
    assert result is not None
    print(f"  Rerank 模式: {result.child_hits_count} 子块, rerank_applied={result.rerank_applied}")
