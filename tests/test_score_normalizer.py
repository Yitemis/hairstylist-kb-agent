# -*- coding: utf-8 -*-
"""Score Normalizer 单测: 不同引擎归一化 + RRF 融合."""
import math
import pytest

from app.rag.retriever.normalizer import (
    NORMALIZERS,
    batch_normalize,
    normalize_score,
    rrf_fuse_normalized,
)


class TestNormalizeScore:
    """测试 normalize_score 各种引擎."""

    def test_milvus_cosine_zero(self):
        """COSINE 0 -> 0.5 (中性)."""
        assert normalize_score(0.0, "milvus_cosine") == 0.5

    def test_milvus_cosine_one(self):
        """COSINE 1.0 -> 1.0 (最高)."""
        assert normalize_score(1.0, "milvus_cosine") == 1.0

    def test_milvus_cosine_minus_one(self):
        """COSINE -1.0 -> 0.0 (最低)."""
        assert normalize_score(-1.0, "milvus_cosine") == 0.0

    def test_milvus_cosine_clip_above(self):
        """> 1.0 clip 到 1.0."""
        assert normalize_score(2.0, "milvus_cosine") == 1.0

    def test_milvus_cosine_clip_below(self):
        """< -1.0 clip 到 0.0."""
        assert normalize_score(-2.0, "milvus_cosine") == 0.0

    def test_milvus_l2_zero(self):
        """L2 0 -> 1.0 (完全相同)."""
        assert normalize_score(0.0, "milvus_l2") == 1.0

    def test_milvus_l2_large(self):
        """L2 大距离 -> 接近 0."""
        v = normalize_score(100.0, "milvus_l2")
        assert 0.0 < v < 0.02

    def test_bm25_zero(self):
        """BM25 0 -> 0.5 (sigmoid 中心)."""
        assert abs(normalize_score(0.0, "bm25") - 0.5) < 1e-6

    def test_bm25_high(self):
        """BM25 5 -> ~0.993."""
        v = normalize_score(5.0, "bm25")
        assert v > 0.99

    def test_rerank_passthrough(self):
        """Rerank 透传."""
        assert normalize_score(0.85, "rerank") == 0.85

    def test_unknown_engine_clips(self):
        """未知引擎: clip 到 [0, 1]."""
        assert normalize_score(2.0, "unknown") == 1.0
        assert normalize_score(-0.5, "unknown") == 0.0

    def test_invalid_input_returns_zero(self):
        """非法输入: bm25/l2 返回 0, cosine 抛错也回 0.5."""
        # BM25 / L2 内部 try/except
        assert normalize_score(None, "bm25") == 0.0
        assert normalize_score(None, "milvus_l2") == 0.0


class TestBatchNormalize:
    """测试批量归一化."""

    def test_basic(self):
        hits = [
            {"id": "1", "score": 0.8, "parent_id": "p1"},
            {"id": "2", "score": 0.0, "parent_id": "p2"},
            {"id": "3", "score": -0.5, "parent_id": "p3"},
        ]
        out = batch_normalize(hits, engine_type="milvus_cosine")
        assert len(out) == 3
        assert out[0]["raw_score"] == 0.8
        assert abs(out[0]["normalized_score"] - 0.9) < 1e-6
        assert out[1]["normalized_score"] == 0.5
        assert out[2]["normalized_score"] == 0.25

    def test_empty_list(self):
        assert batch_normalize([], engine_type="milvus_cosine") == []

    def test_missing_score_field(self):
        """缺 score 字段时默认 0."""
        hits = [{"id": "1", "parent_id": "p1"}]
        out = batch_normalize(hits, engine_type="milvus_cosine")
        assert out[0]["raw_score"] == 0.0
        assert out[0]["normalized_score"] == 0.5


class TestRRFFuseNormalized:
    """测试 RRF 融合 (归一化场景)."""

    def test_single_source(self):
        """单路召回: 排名越前分数越高."""
        v = [
            {"parent_id": "a", "score": 0.9},
            {"parent_id": "b", "score": 0.7},
            {"parent_id": "c", "score": 0.5},
        ]
        fused = rrf_fuse_normalized(v, [], k=60, vector_weight=1.0, bm25_weight=0.0)
        assert [h["parent_id"] for h in fused] == ["a", "b", "c"]

    def test_dual_source_fusion(self):
        """双路融合: vector 和 BM25 都有命中 -> 共同 parent 排名靠前."""
        v = [
            {"parent_id": "a", "score": 0.9, "filename": "doc1"},
            {"parent_id": "b", "score": 0.7, "filename": "doc1"},
        ]
        bm = [
            {"parent_id": "a", "score": 0.8, "content": "content for a", "filename": "doc1"},
            {"parent_id": "c", "score": 0.6, "content": "content for c", "filename": "doc2"},
        ]
        fused = rrf_fuse_normalized(v, bm)
        # 'a' 在两边都出现, 排名应该最前
        assert fused[0]["parent_id"] == "a"
        # 验证 content 合并 (BM25 应该有完整 content)
        assert fused[0].get("content") == "content for a"

    def test_empty_inputs(self):
        assert rrf_fuse_normalized([], []) == []

    def test_rrf_score_ordering(self):
        """RRF 分数严格降序."""
        v = [{"parent_id": f"p{i}", "score": 0.5} for i in range(5)]
        bm = [{"parent_id": f"p{i}", "score": 0.5} for i in range(5)]
        fused = rrf_fuse_normalized(v, bm)
        scores = [h["rrf_score"] for h in fused]
        assert scores == sorted(scores, reverse=True)
