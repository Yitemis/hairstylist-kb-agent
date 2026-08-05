# -*- coding: utf-8 -*-
"""RAG 评估 runner: 跑评估集, 计算指标, 输出报告。

借鉴 LangChain/LlamaIndex evaluation 框架。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.rag.evaluation.eval_set import EVAL_SET, EvalQuery
from app.rag.evaluation.metrics import (
    aggregate_metrics, hit_rate, mrr, ndcg_at_k, recall_at_k,
)

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """单个 query 的评估结果。"""
    query: str
    category: str
    difficulty: str
    expected_keywords: list[str]
    retrieved_count: int
    top_docs: list[str]
    recall_at_5: float
    recall_at_10: float
    mrr: float
    hit_rate_at_5: float
    ndcg_at_5: float
    latency_ms: int


async def evaluate_query(
    eq: EvalQuery,
    retrieve_fn,
    top_k: int = 10,
) -> EvalResult:
    """评估单个 query。

    Args:
        eq: 评估 query
        retrieve_fn: 检索函数 (query, tenant_id, top_k) -> RetrievalResult
        top_k: 检索数量
    """
    t0 = time.time()
    try:
        # 用默认 tenant 评估
        result = await retrieve_fn(eq.query, "demo", top_k)
        # 提取文档内容
        docs = [h.content for h in result.hits if h.content]
    except Exception as e:
        logger.warning("Eval query failed: %s | %s", eq.query, e)
        docs = []
    latency = int((time.time() - t0) * 1000)

    return EvalResult(
        query=eq.query,
        category=eq.category,
        difficulty=getattr(eq, "difficulty", "easy"),
        expected_keywords=eq.expected_keywords,
        retrieved_count=len(docs),
        top_docs=docs[:3],  # 保留前 3 个
        recall_at_5=recall_at_k(docs, eq.expected_keywords, 5),
        recall_at_10=recall_at_k(docs, eq.expected_keywords, 10),
        mrr=mrr(docs, eq.expected_keywords),
        hit_rate_at_5=hit_rate(docs, eq.expected_keywords, 5),
        ndcg_at_5=ndcg_at_k(docs, eq.expected_keywords, 5),
        latency_ms=latency,
    )


async def run_evaluation(
    retrieve_fn,
    eval_set: list = None,
    top_k: int = 10,
    lang: str = "zh",
) -> dict:
    """跑完整评估集，返回聚合报告。

    Args:
        retrieve_fn: 检索函数
        eval_set: 评估集 (默认用 EVAL_SET)
        top_k: 检索数量

    Returns:
        {
            "summary": {"count": 30, "recall_at_5": 0.7, ...},
            "per_query": [EvalResult, ...],
            "by_category": {"knowledge": {...}, "booking": {...}}
        }
    """
    if eval_set is None:
        if lang == "en":
            from app.rag.evaluation.eval_set_en import EVAL_SET_EN
            eval_set = EVAL_SET_EN
        else:
            eval_set = EVAL_SET

    per_query = []
    for eq in eval_set:
        r = await evaluate_query(eq, retrieve_fn, top_k)
        per_query.append(r)

    # 聚合
    summary = aggregate_metrics([vars(r) for r in per_query])

    # 按 category 分组
    by_category = {}
    for cat in set(r.category for r in per_query):
        cat_results = [vars(r) for r in per_query if r.category == cat]
        by_category[cat] = aggregate_metrics(cat_results)

    return {
        "summary": summary,
        "by_category": by_category,
        "per_query": per_query,
    }


def format_report(report: dict) -> str:
    """格式化为可读报告。"""
    lines = ["=" * 60, "RAG Evaluation Report", "=" * 60]
    s = report["summary"]
    lines.append(f"\n[Overall] count={s['count']}")
    for k, v in s.items():
        if k != "count":
            lines.append(f"  {k}: {v:.3f}")

    lines.append(f"\n[By Category]")
    for cat, m in report["by_category"].items():
        lines.append(f"  {cat}: recall_at_5={m['recall_at_5']:.3f} mrr={m['mrr']:.3f} hit_rate_at_5={m['hit_rate_at_5']:.3f} n={m['count']}")

    # 失败案例
    lines.append(f"\n[Top 5 Failed Queries]")
    failed = [r for r in report["per_query"] if r.recall_at_5 < 0.3 and r.expected_keywords]
    failed.sort(key=lambda r: r.recall_at_5)
    for r in failed[:5]:
        lines.append(f"  [{r.category}] {r.query[:40]}... -> recall_at_5={r.recall_at_5:.2f} latency={r.latency_ms}ms")

    return "\n".join(lines)
