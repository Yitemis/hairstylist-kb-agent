# -*- coding: utf-8 -*-
"""检索结果融合：Reciprocal Rank Fusion (RRF)。

向量检索与 BM25 的分数量纲不同（余弦相似度 vs 词频统计），不能直接相加。
RRF 只依赖每个通道内的排名，用 ``1/(k + rank)`` 累加，天然对齐量纲、鲁棒性
好，是多路召回融合的常用做法。

也支持给某一路加权（``weights``），例如更信任向量或更信任关键词。
"""
from __future__ import annotations

from collections import defaultdict


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    weights: list[float] | None = None,
    k: int = 60,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """对多路排名结果做 RRF 融合。

    Args:
        ranked_lists: 每一路的 doc_id 排名列表（下标即排名，越靠前越相关）。
        weights: 每一路的权重，缺省全为 1.0。
        k: RRF 平滑常数，越大则高排名的优势越弱（经验值 60）。
        top_k: 只返回前 top_k 条，缺省返回全部。

    Returns:
        融合后的 ``(doc_id, fused_score)``，按分数降序。
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights 数量需与 ranked_lists 一致")

    fused: dict[str, float] = defaultdict(float)
    for ranking, weight in zip(ranked_lists, weights):
        for rank, doc_id in enumerate(ranking):
            fused[doc_id] += weight * (1.0 / (k + rank + 1))

    result = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return result[:top_k] if top_k else result
