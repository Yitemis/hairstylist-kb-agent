# -*- coding: utf-8 -*-
"""RAG 评估指标。

- Recall@k: 前 k 个结果中包含正确答案的比例
- MRR (Mean Reciprocal Rank): 第一个正确答案排名的倒数
- NDCG@k: 归一化折损累积增益
- Hit Rate: 至少有一个相关结果的 query 比例
"""
from __future__ import annotations

import math
from typing import List, Optional


def recall_at_k(
    retrieved_docs: list[str],
    expected_keywords: list[str],
    k: int = 5,
) -> float:
    """Recall@k: 检索结果中是否包含期望关键词。

    Args:
        retrieved_docs: 检索到的文档内容列表
        expected_keywords: 期望答案中的关键词
        k: top-k

    Returns:
        1.0 if any expected_keyword found in top-k, else 0.0
    """
    if not expected_keywords:
        return 1.0  # 闲聊/无期望 -> 默认满分
    top_k_text = " ".join(retrieved_docs[:k]).lower()
    matched = sum(1 for kw in expected_keywords if kw.lower() in top_k_text)
    return min(1.0, matched / max(1, len(expected_keywords) * 0.3))


def mrr(
    retrieved_docs: list[str],
    expected_keywords: list[str],
) -> float:
    """Mean Reciprocal Rank: 第一个正确结果的排名倒数。

    Returns:
        1/rank if found, 0.0 if not found
    """
    if not expected_keywords:
        return 1.0
    for i, doc in enumerate(retrieved_docs, 1):
        text = doc.lower()
        if any(kw.lower() in text for kw in expected_keywords):
            return 1.0 / i
    return 0.0


def hit_rate(
    retrieved_docs: list[str],
    expected_keywords: list[str],
    k: int = 5,
) -> float:
    """Hit Rate: top-k 中是否命中。"""
    return float(recall_at_k(retrieved_docs, expected_keywords, k) > 0)


def ndcg_at_k(
    retrieved_docs: list[str],
    expected_keywords: list[str],
    k: int = 5,
) -> float:
    """NDCG@k: 归一化折损累积增益。"""
    if not expected_keywords:
        return 1.0
    # DCG
    dcg = 0.0
    for i, doc in enumerate(retrieved_docs[:k], 1):
        rel = 1.0 if any(kw.lower() in doc.lower() for kw in expected_keywords) else 0.0
        dcg += rel / math.log2(i + 1)
    # IDCG (理想: 前 k 个位置全部相关)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, k + 1))
    if idcg == 0:
        return 0.0
    return min(1.0, dcg / idcg)


def aggregate_metrics(per_query_results: list[dict]) -> dict:
    """聚合多个 query 的指标。"""
    if not per_query_results:
        return {"count": 0}
    metrics = ["recall_at_5", "recall_at_10", "mrr", "hit_rate_at_5", "ndcg_at_5"]
    return {
        "count": len(per_query_results),
        **{m: sum(r.get(m, 0) for r in per_query_results) / len(per_query_results) for m in metrics},
    }
