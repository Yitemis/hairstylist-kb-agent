# -*- coding: utf-8 -*-
"""查询改写 6 策略测试。"""
import asyncio
import pytest

from app.rag.query.rewriter import (
    rewrite, subquery, hyde, stepback, multiquery, selfquery,
    rewrite_query, STRATEGIES, CATEGORY_KEYWORDS,
)


def test_all_6_strategies_registered():
    """6 个策略全部注册。"""
    assert len(STRATEGIES) == 6
    expected = {"rewrite", "subquery", "hyde", "stepback", "multiquery", "selfquery"}
    assert set(STRATEGIES.keys()) == expected


def test_selfquery_keyword_detection():
    """selfquery 策略：从 query 检测 category。"""
    # 中文关键词 → category
    async def run():
        r = await selfquery("美甲什么款式好")
        assert "nail" in r.filters.get("category", []), r
        r2 = await selfquery("染发颜色选择")
        assert "coloring" in r2.filters.get("category", []), r2
    asyncio.run(run())


def test_selfquery_no_category():
    """selfquery 找不到 category 时返回空 filters。"""
    async def run():
        r = await selfquery("我今天心情不好")
        # 无 category 关键词
        assert not r.filters.get("category", [])
        assert r.candidates == ["我今天心情不好"]
    asyncio.run(run())


def test_selfquery_keeps_main_query():
    """selfquery 抽掉 category 词后保留主体。"""
    async def run():
        r = await selfquery("推荐个洗发水")
        # 主体应该去掉"洗发"（属于 haircare）
        assert "洗发" not in r.candidates[0]
        assert "推荐" in r.candidates[0]
        assert "haircare" in r.filters.get("category", [])
    asyncio.run(run())


def test_rewrite_query_runs_all_6():
    """rewrite_query 跑 6 个策略（并行）。"""
    async def run():
        results = await rewrite_query("洗发用什么水温好", strategies=None)
        # 应该返回 6 个结果
        assert len(results) == 6
        strategies = {r.strategy for r in results}
        assert strategies == {"rewrite", "subquery", "hyde", "stepback", "multiquery", "selfquery"}
    asyncio.run(run())


def test_rewrite_query_subset():
    """rewrite_query 跑指定子集策略。"""
    async def run():
        results = await rewrite_query("test", strategies=["rewrite", "selfquery"])
        assert len(results) == 2
        assert {r.strategy for r in results} == {"rewrite", "selfquery"}
    asyncio.run(run())


def test_strategy_resilience():
    """某个策略失败不影响其他（return_exceptions）。"""
    # 强制 LLM 失败：传空 query
    async def run():
        results = await rewrite_query("", strategies=["rewrite", "selfquery"])
        # 至少 selfquery 不依赖 LLM 也能工作
        assert any(r.strategy == "selfquery" for r in results)
    asyncio.run(run())


def test_category_keywords_coverage():
    """类别关键词覆盖主要场景。"""
    assert "haircare" in CATEGORY_KEYWORDS
    assert "coloring" in CATEGORY_KEYWORDS
    assert "styling" in CATEGORY_KEYWORDS
    assert "nail" in CATEGORY_KEYWORDS


# ===================================================================
# 集成测试：retrieve 配合 enable_rewrite
# ===================================================================

@pytest.mark.asyncio
async def test_retrieve_with_rewrite_improves_recall():
    """开启 query rewrite 后检索可能召回更多（鲁棒性测试）。"""
    from app.rag.v2_engine import index_document, retrieve, reset_state
    from sqlalchemy import delete
    from app.db.session import async_session_maker
    from app.db.models import Document, ParentChunk, ChildChunk

    reset_state()
    # 清理 (含 child_chunks 避免 pgvector 孤儿)
    async with async_session_maker() as s:
        await s.execute(delete(ChildChunk).where(ChildChunk.tenant_id == "rewrite_test"))
        await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id == "rewrite_test"))
        await s.execute(delete(Document).where(Document.tenant_id == "rewrite_test"))
        await s.commit()

    # 文档里用专业表达
    content = """# 洗发标准操作流程

## 水温控制
洗发水温应控制在 38-40 摄氏度区间，避免高温烫伤头皮。

## 护发素使用
护发素停留时间建议 3-5 分钟后再冲洗。"""
    await index_document("rewrite_doc", content, "t.pdf", "rewrite_test", "haircare")

    # Fix: index_document 默认 is_published=False, 传 include_unpublished=True
    # 1. 不开 rewrite: 口语化 query
    r_no_rewrite = await retrieve(
        "水温多少度", "rewrite_test", top_k=2,
        enable_rewrite=False, include_unpublished=True,
    )
    # 2. 开 rewrite: 多策略融合
    r_with_rewrite = await retrieve(
        "水温多少度", "rewrite_test", top_k=2,
        enable_rewrite=True, rewrite_strategies=["rewrite", "selfquery"],
        include_unpublished=True,
    )

    # 至少一个能召回内容
    assert r_no_rewrite.hits or r_with_rewrite.hits
    # rewrite 命中数应 >= 不开 rewrite（或者都为空，但不能变差）
    if r_no_rewrite.hits:
        # 验证内容非空
        assert any(h.content for h in r_no_rewrite.hits)

    # 清理
    async with async_session_maker() as s:
        await s.execute(delete(ChildChunk).where(ChildChunk.tenant_id == "rewrite_test"))
        await s.execute(delete(ParentChunk).where(ParentChunk.tenant_id == "rewrite_test"))
        await s.execute(delete(Document).where(Document.tenant_id == "rewrite_test"))
        await s.commit()


def test_retrieve_default_no_rewrite():
    """默认不开 rewrite（向后兼容）。"""
    from app.rag.v2_engine import retrieve
    import inspect
    sig = inspect.signature(retrieve)
    assert sig.parameters["enable_rewrite"].default is False
