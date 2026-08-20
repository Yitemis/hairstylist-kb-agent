# -*- coding: utf-8 -*-
"""Self-RAG unit tests."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.rag.agentic.self_rag import (
    RetrievalEvaluation,
    evaluate_retrieval_confidence,
    self_rag_retrieve,
)


class FakeHit:
    def __init__(self, score, content=""):
        self.score = score
        self.content = content


class TestEvaluateConfidence:
    """Test evaluate_retrieval_confidence."""

    @pytest.mark.asyncio
    async def test_no_hits_needs_retry(self):
        eval = await evaluate_retrieval_confidence("test", [], use_llm=False)
        assert eval.needs_retry is True
        assert eval.confidence == 0.0
        assert "no retrieval" in eval.reason

    @pytest.mark.asyncio
    async def test_high_score_no_retry(self):
        hits = [FakeHit(0.9), FakeHit(0.7), FakeHit(0.5)]
        eval = await evaluate_retrieval_confidence("test", hits, use_llm=False)
        assert eval.needs_retry is False
        assert eval.confidence >= 0.6

    @pytest.mark.asyncio
    async def test_low_score_needs_retry(self):
        hits = [FakeHit(0.1), FakeHit(0.05), FakeHit(0.0)]
        eval = await evaluate_retrieval_confidence("test", hits, use_llm=False)
        assert eval.needs_retry is True
        assert "low" in eval.reason.lower()

    @pytest.mark.asyncio
    async def test_dict_hits(self):
        hits = [
            {"score": 0.8, "content": "test1"},
            {"score": 0.6, "content": "test2"},
        ]
        eval = await evaluate_retrieval_confidence("test", hits, use_llm=False)
        assert eval.needs_retry is False

    @pytest.mark.asyncio
    async def test_normalized_score_priority(self):
        # normalized_score 应该优先于 raw score
        hits = [
            {"score": 0.1, "normalized_score": 0.9, "content": "test"},
        ]
        eval = await evaluate_retrieval_confidence("test", hits, use_llm=False)
        # normalized=0.9, top1 >= 0.6
        assert eval.needs_retry is False


class TestSelfRAGRetrieve:
    """Test self_rag_retrieve main entry."""

    @pytest.mark.asyncio
    async def test_pass_on_first_try(self):
        # Mock retrieve_fn 返回高分 hits
        mock_result = MagicMock()
        mock_result.hits = [FakeHit(0.9), FakeHit(0.8)]

        async def retrieve_fn(query, tenant_id, top_k):
            return mock_result

        out = await self_rag_retrieve(
            query="test",
            retrieve_fn=retrieve_fn,
            max_retries=2,
        )
        assert out["attempts"] == 1
        assert out["evaluation"].needs_retry is False

    @pytest.mark.asyncio
    async def test_retry_then_pass(self):
        call_count = {"n": 0}

        async def retrieve_fn(query, tenant_id, top_k):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                # 第一次: 低分
                mock_result.hits = [FakeHit(0.1), FakeHit(0.05)]
            else:
                # 第二次: 高分
                mock_result.hits = [FakeHit(0.9), FakeHit(0.8)]
            return mock_result

        out = await self_rag_retrieve(
            query="test",
            retrieve_fn=retrieve_fn,
            max_retries=3,
        )
        assert call_count["n"] >= 2
        assert out["attempts"] >= 2

    @pytest.mark.asyncio
    async def test_max_retries_respected(self):
        call_count = {"n": 0}

        async def retrieve_fn(query, tenant_id, top_k):
            call_count["n"] += 1
            mock_result = MagicMock()
            mock_result.hits = [FakeHit(0.1)]  # 一直低分
            return mock_result

        out = await self_rag_retrieve(
            query="test",
            retrieve_fn=retrieve_fn,
            max_retries=2,
        )
        # 1 initial + 2 retries = 3 calls
        assert call_count["n"] == 3
        assert out["attempts"] == 3

    @pytest.mark.asyncio
    async def test_rewrite_history_tracked(self):
        async def retrieve_fn(query, tenant_id, top_k):
            mock_result = MagicMock()
            mock_result.hits = [FakeHit(0.1)]
            return mock_result

        out = await self_rag_retrieve(
            query="original query",
            retrieve_fn=retrieve_fn,
            max_retries=2,
        )
        # rewrite_history 应该有多个 query
        assert len(out["rewrite_history"]) >= 1
        assert out["rewrite_history"][0] == "original query"
