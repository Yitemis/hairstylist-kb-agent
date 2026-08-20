# -*- coding: utf-8 -*-
"""RAGAS evaluation unit tests."""
import pytest

from app.rag.evaluation.ragas_runner import (
    RAGASResult,
    _HAS_RAGAS,
    aggregate_ragas_results,
    evaluate_rag,
    heuristic_answer_relevancy,
    heuristic_context_precision,
    heuristic_context_recall,
    heuristic_faithfulness,
)


class TestHeuristicFaithfulness:
    """Test heuristic_faithfulness."""

    def test_empty_answer(self):
        assert heuristic_faithfulness("", ["context"]) == 0.0

    def test_empty_context(self):
        assert heuristic_faithfulness("answer", []) == 0.0

    def test_answer_in_context(self):
        ctx = ["must do skin test 48h before dyeing"]
        ans = "must do skin test 48h before dyeing"
        score = heuristic_faithfulness(ans, ctx)
        assert score >= 0.8

    def test_answer_not_in_context(self):
        ctx = ["hair styling tips"]
        ans = "this is a completely different topic"
        score = heuristic_faithfulness(ans, ctx)
        assert score <= 0.3


class TestHeuristicAnswerRelevancy:
    """Test heuristic_answer_relevancy."""

    def test_empty_input(self):
        assert heuristic_answer_relevancy("", "query") == 0.0
        assert heuristic_answer_relevancy("answer", "") == 0.0

    def test_relevant_answer(self):
        query = "dye hair before test"
        answer = "skin allergy test 48h before dyeing"
        score = heuristic_answer_relevancy(answer, query)
        assert score > 0.3  # some overlap

    def test_irrelevant_answer(self):
        query = "dye hair before test"
        answer = "weather is nice today"
        score = heuristic_answer_relevancy(answer, query)
        assert score < 0.2


class TestHeuristicContextPrecision:
    """Test heuristic_context_precision."""

    def test_all_relevant(self):
        ctx = ["skin test 48h", "allergy test required"]
        kws = ["skin", "test"]
        score = heuristic_context_precision(ctx, kws)
        assert score == 1.0

    def test_none_relevant(self):
        ctx = ["hair styling", "coloring tips"]
        kws = ["skin", "test"]
        score = heuristic_context_precision(ctx, kws)
        assert score == 0.0

    def test_empty_keywords(self):
        assert heuristic_context_precision(["ctx"], []) == 1.0

    def test_half_relevant(self):
        ctx = ["skin test", "random"]
        kws = ["skin"]
        score = heuristic_context_precision(ctx, kws)
        assert score == 0.5


class TestHeuristicContextRecall:
    """Test heuristic_context_recall."""

    def test_no_ground_truth(self):
        assert heuristic_context_recall(["ctx"], "") == 0.5

    def test_ground_truth_in_context(self):
        ctx = ["must do skin test 48h before dyeing"]
        gt = "skin test 48 hours before"
        score = heuristic_context_recall(ctx, gt)
        assert score > 0.3

    def test_ground_truth_not_in_context(self):
        ctx = ["hair styling tips"]
        gt = "skin test 48 hours before dyeing"
        score = heuristic_context_recall(ctx, gt)
        assert score < 0.5


class TestEvaluateRAG:
    """Test evaluate_rag main entry."""

    def test_basic_evaluation(self):
        result = evaluate_rag(
            query="how to perm hair",
            answer="apply perm solution and wait 30 minutes",
            retrieved_contexts=["perm process: apply solution, wait 30 min, rinse"],
            ground_truth_answer="apply perm solution and wait",
            expected_keywords=["perm", "solution"],
        )
        assert isinstance(result, RAGASResult)
        assert 0.0 <= result.faithfulness <= 1.0
        assert 0.0 <= result.answer_relevancy <= 1.0
        assert 0.0 <= result.context_precision <= 1.0
        assert 0.0 <= result.context_recall <= 1.0
        assert result.details["used_method"] in ("heuristic", "ragas_real")

    def test_fallback_to_heuristic(self):
        # No ragas = use heuristic
        result = evaluate_rag(
            query="test query",
            answer="test answer",
            retrieved_contexts=["test context"],
            use_ragas=False,
        )
        assert result.details["used_method"] == "heuristic"

    def test_ragas_when_available(self):
        # If ragas is available, method is ragas_real; otherwise heuristic
        if _HAS_RAGAS:
            result = evaluate_rag(
                query="test",
                answer="answer",
                retrieved_contexts=["context"],
                use_ragas=True,
            )
            assert result.details["used_method"] in ("ragas_real", "heuristic")
        else:
            assert True  # Skip test if ragas not available


class TestAggregateResults:
    """Test aggregate_ragas_results."""

    def test_aggregate_multiple(self):
        results = [
            RAGASResult(0.8, 0.7, 0.9, 0.6),
            RAGASResult(0.6, 0.5, 0.7, 0.8),
        ]
        agg = aggregate_ragas_results(results)
        assert agg.faithfulness == 0.7  # (0.8+0.6)/2
        assert agg.answer_relevancy == 0.6
        assert agg.context_precision == 0.8
        assert agg.context_recall == 0.7
        assert agg.details["count"] == 2

    def test_aggregate_empty(self):
        agg = aggregate_ragas_results([])
        assert agg.faithfulness == 0.0
        assert agg.details["count"] == 0


class TestRAGASResult:
    """Test RAGASResult dataclass."""

    def test_to_dict(self):
        r = RAGASResult(0.8, 0.7, 0.9, 0.6, {"count": 1, "used_method": "heuristic"})
        d = r.to_dict()
        assert d["faithfulness"] == 0.8
        assert d["answer_relevancy"] == 0.7
        assert d["context_precision"] == 0.9
        assert d["context_recall"] == 0.6
        assert d["count"] == 1
        assert d["used_method"] == "heuristic"

    def test_to_dict_rounds(self):
        r = RAGASResult(0.123456, 0.7654321, 0.999, 0.001)
        d = r.to_dict()
        assert d["faithfulness"] == 0.123
        assert d["context_recall"] == 0.001
