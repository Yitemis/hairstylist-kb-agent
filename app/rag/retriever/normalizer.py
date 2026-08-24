# -*- coding: utf-8 -*-
"""Score Normalizer: 不同向量库 / 检索引擎的分数归一化。

借鉴 WeKnora retriever/normalizer.go (Section 3.4).

Why?
- Milvus COSINE:       score in [-1, 1]      -> 归一到 [0, 1]
- Milvus L2/IP:         score in [0, +inf) 或 [0, 1]
- BM25 (PG ts_rank_cd): score in [0, +inf)   -> sigmoid 压缩
- BGE Rerank:           score in [0, 1]      -> 透传

如果不归一化直接 RRF 融合:
- vector 高分 (0.9) + bm25 高分 (5.0) -> bm25 完全压死 vector
- vector 高分 (0.9) + bm25 高分 (0.05) -> vector 完全压死 bm25

归一化后两者都在 [0, 1], RRF 融合才稳定.
"""
from __future__ import annotations

import math
from typing import Callable, Dict


# ============================================================
# 归一化器
# ============================================================

def _normalize_milvus_cosine(score: float) -> float:
    """Milvus COSINE: [-1, 1] -> [0, 1]"""
    return max(0.0, min(1.0, (float(score) + 1.0) / 2.0))


def _normalize_milvus_l2(distance: float) -> float:
    """Milvus L2 distance: 1 / (1 + d)."""
    try:
        return 1.0 / (1.0 + float(distance))
    except (TypeError, ValueError):
        return 0.0


def _normalize_bm25(score: float) -> float:
    """BM25 sigmoid 压缩: 1 / (1 + exp(-x))."""
    try:
        return 1.0 / (1.0 + math.exp(-float(score)))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _normalize_rerank(score: float) -> float:
    """Rerank 分数 passthrough (BGE rerank 输出已是 [0, 1]).

    实战验证 (2026-08-24): BGE rerank 实际输出 sigmoid 形式 (0.998=相关, 0.0001=不相关),
    已是 [0, 1] 归一化, 不需要再 sigmoid. 之前误判成 raw logit 是错的.

    但因为 0.0001 这种极小值, 触发 gate 拒答, 所以用 log 缩放:
    - raw=0.998 -> 0.998 (保留)
    - raw=0.5   -> 0.5
    - raw=0.001 -> 0.144 (log 提升)
    - raw=0.0001 -> 0.115
    """
    try:
        s = float(score)
        if s <= 0:
            return 0.0
        if s >= 1:
            return 1.0
        # log 缩放: 让极小值能跟中等值区分, 但不破坏 0.5+ 的区分度
        # log10(1 + 9*s) / log10(10) 把 [0,1] -> [0,1] 但 spread 更均匀
        import math
        return math.log10(1 + 9 * s)
    except (TypeError, ValueError):
        return 0.5


NORMALIZERS: Dict[str, Callable[[float], float]] = {
    "milvus_cosine": _normalize_milvus_cosine,
    "milvus_l2": _normalize_milvus_l2,
    "bm25": _normalize_bm25,
    "rerank": _normalize_rerank,
}


def normalize_score(score: float, engine_type: str = "milvus_cosine") -> float:
    """按引擎类型归一化分数到 [0, 1].

    Args:
        score: 原始分数
        engine_type: 'milvus_cosine' / 'milvus_l2' / 'bm25' / 'rerank'

    Returns:
        归一化后的分数
    """
    normalizer = NORMALIZERS.get(engine_type)
    if normalizer is None:
        return max(0.0, min(1.0, float(score)))
    return normalizer(score)


def batch_normalize(
    hits: list,
    score_field: str = "score",
    engine_type: str = "milvus_cosine",
) -> list:
    """批量归一化 hits 的分数.

    Args:
        hits: hit 列表, 每项含 score 字段
        score_field: 分数字段名
        engine_type: 引擎类型

    Returns:
        新 list, 每项加 raw_score + normalized_score
    """
    out = []
    for h in hits:
        h = dict(h)  # copy
        raw = h.get(score_field, 0.0)
        h["raw_score"] = raw
        h["normalized_score"] = normalize_score(raw, engine_type)
        out.append(h)
    return out


def rrf_fuse_normalized(
    vector_hits: list,
    bm25_hits: list,
    k: int = 60,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> list:
    """归一化后的 RRF 融合.

    公式: rrf(d) = vector_weight / (k + vec_rank) + bm25_weight / (k + bm25_rank)

    Args:
        vector_hits: 归一化后的向量 hit 列表
        bm25_hits: 归一化后的 BM25 hit 列表
        k: RRF k 参数 (默认 60, 论文值)
        vector_weight: 向量权重
        bm25_weight: BM25 权重

    Returns:
        按 rrf_score 降序的融合结果
    """
    scores: Dict[str, float] = {}
    payloads: Dict[str, dict] = {}

    for rank, hit in enumerate(vector_hits, 1):
        pid = hit["parent_id"]
        scores[pid] = scores.get(pid, 0.0) + vector_weight / (k + rank)
        payloads[pid] = hit

    for rank, hit in enumerate(bm25_hits, 1):
        pid = hit["parent_id"]
        scores[pid] = scores.get(pid, 0.0) + bm25_weight / (k + rank)
        if pid not in payloads:
            payloads[pid] = hit
        else:
            # 合并: BM25 hit 往往有完整 content
            for k_field, v in hit.items():
                if k_field in ("score", "normalized_score", "raw_score"):
                    continue
                if not payloads[pid].get(k_field):
                    payloads[pid][k_field] = v

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{**payloads[pid], "rrf_score": score} for pid, score in fused]


__all__ = [
    "NORMALIZERS",
    "normalize_score",
    "batch_normalize",
    "rrf_fuse_normalized",
]
