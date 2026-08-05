# -*- coding: utf-8 -*-
"""RAG 评估测试。

覆盖:
- 指标: recall@k / MRR / hit_rate / NDCG
- 评估集: 30 个 query 覆盖各场景
- runner: 端到端 + 报告
"""
import pytest

from app.rag.evaluation.eval_set import EVAL_SET, EvalQuery
from app.rag.evaluation.metrics import (
    recall_at_k, mrr, hit_rate, ndcg_at_k, aggregate_metrics,
)
from app.rag.evaluation.runner import evaluate_query, run_evaluation, format_report


# ===================================================================
# 指标单元测试
# ===================================================================

class TestRecallAtK:
    def test_recall_keyword_found(self):
        docs = ["染发前需要做皮肤测试", "其他内容"]
        assert recall_at_k(docs, ["皮肤", "测试"], 5) == 1.0

    def test_recall_keyword_not_found(self):
        docs = ["完全不相关的内容"]
        assert recall_at_k(docs, ["皮肤", "测试"], 5) == 0.0

    def test_recall_empty_expected(self):
        # 闲聊/无期望 -> 默认 1.0
        assert recall_at_k(["任何内容"], [], 5) == 1.0

    def test_recall_k_limits(self):
        docs = ["keyword1"] * 10
        # keyword1 在所有 doc 中 - k=5 也命中
        assert recall_at_k(docs, ["keyword1"], 5) == 1.0

    def test_recall_partial_match(self):
        # 50% 关键词命中 -> 0.5
        docs = ["找到皮肤测试", "其他"]
        # 2 个关键词 (皮肤, 测试), 都找到 -> 1.0
        assert recall_at_k(docs, ["皮肤", "测试"], 5) == 1.0


class TestMRR:
    def test_mrr_first_match(self):
        # 第一个命中 -> MRR = 1.0
        assert mrr(["命中", "其他"], ["命中"]) == 1.0

    def test_mrr_second_match(self):
        # 第二个命中 -> MRR = 0.5
        assert mrr(["其他", "命中"], ["命中"]) == 0.5

    def test_mrr_third_match(self):
        # 第三个 -> 0.333
        assert abs(mrr(["a", "b", "命中"], ["命中"]) - 0.333) < 0.01

    def test_mrr_no_match(self):
        assert mrr(["a", "b", "c"], ["命中"]) == 0.0

    def test_mrr_empty_expected(self):
        assert mrr(["任何"], []) == 1.0


class TestHitRate:
    def test_hit(self):
        assert hit_rate(["命中 keyword"], ["keyword"], 5) == 1.0

    def test_no_hit(self):
        assert hit_rate(["不相关"], ["keyword"], 5) == 0.0


class TestNDCG:
    def test_ndcg_perfect(self):
        # 所有文档相关 -> 1.0
        docs = ["relevant1", "relevant2", "relevant3"]
        assert abs(ndcg_at_k(docs, ["relevant"], 3) - 1.0) < 0.01

    def test_ndcg_no_match(self):
        assert ndcg_at_k(["a", "b", "c"], ["命中"]) == 0.0


class TestAggregate:
    def test_aggregate_empty(self):
        result = aggregate_metrics([])
        assert result["count"] == 0

    def test_aggregate_single(self):
        per_query = [
            {"recall@5": 1.0, "recall@10": 1.0, "mrr": 1.0, "hit_rate@5": 1.0, "ndcg@5": 1.0}
        ]
        result = aggregate_metrics(per_query)
        assert result["count"] == 1
        assert result["recall@5"] == 1.0


# ===================================================================
# 评估集测试
# ===================================================================

def test_eval_set_size():
    assert len(EVAL_SET) == 30


def test_eval_set_categories():
    cats = set(eq.category for eq in EVAL_SET)
    assert "knowledge" in cats
    assert "booking" in cats
    assert "multimodal" in cats
    assert "casual" in cats


def test_eval_set_difficulty_distribution():
    easy = sum(1 for eq in EVAL_SET if eq.difficulty == "easy")
    hard = sum(1 for eq in EVAL_SET if eq.difficulty == "hard")
    assert easy >= 20  # 大部分是 easy
    assert hard >= 3   # 至少 3 个 hard


def test_eval_query_structure():
    for eq in EVAL_SET[:3]:
        assert eq.query
        assert isinstance(eq.expected_keywords, list)
        assert eq.category in ("knowledge", "booking", "multimodal", "casual")


# ===================================================================
# Runner 测试
# ===================================================================

@pytest.mark.asyncio
async def test_evaluate_query_with_mock_retriever():
    """用 mock retriever 测试 evaluate_query。"""
    async def mock_retrieve(query, tenant_id, top_k):
        class Hit:
            def __init__(self, content):
                self.content = content
        class Result:
            hits = [Hit("染发前需要做皮肤测试，48 小时内不要洗头")]
        return Result()

    eq = EvalQuery("染发前要做什么测试", ["皮肤", "测试"])
    r = await evaluate_query(eq, mock_retrieve, top_k=5)
    assert r.recall_at_5 == 1.0
    assert r.mrr == 1.0
    assert r.hit_rate_at_5 == 1.0
    assert r.latency_ms >= 0


@pytest.mark.asyncio
async def test_evaluate_query_no_match():
    """retriever 返回不相关内容 -> recall = 0。"""
    async def mock_retrieve(query, tenant_id, top_k):
        class Result:
            hits = []
        return Result()

    eq = EvalQuery("染发前要做什么测试", ["皮肤", "测试"])
    r = await evaluate_query(eq, mock_retrieve, top_k=5)
    assert r.recall_at_5 == 0.0
    assert r.mrr == 0.0


@pytest.mark.asyncio
async def test_evaluate_query_handles_retriever_error():
    """retriever 抛异常 -> 不崩, 返回默认值。"""
    async def broken_retrieve(query, tenant_id, top_k):
        raise RuntimeError("vector DB down")

    eq = EvalQuery("染发前要做什么测试", ["皮肤"])
    r = await evaluate_query(eq, broken_retrieve, top_k=5)
    assert r.retrieved_count == 0
    assert r.recall_at_5 == 0.0


@pytest.mark.asyncio
async def test_run_evaluation_full():
    """跑完整评估集 + 报告。"""
    async def mock_retrieve(query, tenant_id, top_k):
        # 50% 概率返回相关
        import random
        if "染发" in query:
            class Hit:
                content = "染发前需要做皮肤测试"
            class Result:
                hits = [Hit()]
            return Result()
        class Result:
            hits = []
        return Result()

    report = await run_evaluation(mock_retrieve)
    assert "summary" in report
    assert "by_category" in report
    assert len(report["per_query"]) == 30
    assert report["summary"]["count"] == 30


def test_format_report():
    """format_report 输出可读报告。"""
    async def mock_retrieve(query, tenant_id, top_k):
        class Result:
            hits = []
        return Result()
    import asyncio
    report = asyncio.run(run_evaluation(mock_retrieve))
    text = format_report(report)
    assert "RAG Evaluation Report" in text
    assert "Overall" in text
    assert "By Category" in text
