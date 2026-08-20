# -*- coding: utf-8 -*-
"""Self-RAG: Agent 评估检索结果, 低 confidence 时自动重检索.

借鉴 AgentScope section 3.1 + WeKnora section 5.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalEvaluation:
    """对单次 retrieval 的评估结果."""
    confidence: float
    relevance: float
    coverage: float
    needs_retry: bool
    reason: str = ""
    suggested_rewrite: Optional[str] = None


async def evaluate_retrieval_confidence(
    query: str,
    hits: List[Any],
    use_llm: bool = True,
) -> RetrievalEvaluation:
    """评估检索结果的可信度."""
    if not hits:
        return RetrievalEvaluation(
            confidence=0.0, relevance=0.0, coverage=0.0,
            needs_retry=True, reason="no retrieval results",
        )

    scores: List[float] = []
    for h in hits:
        if isinstance(h, dict):
            s = h.get("normalized_score", h.get("score", 0.0))
        else:
            s = float(getattr(h, "score", 0.0) or 0.0)
        scores.append(s)

    if not scores:
        return RetrievalEvaluation(
            confidence=0.0, relevance=0.0, coverage=0.0,
            needs_retry=True, reason="no valid scores",
        )

    top1 = max(scores)
    avg = sum(scores) / len(scores)
    coverage = min(1.0, len([s for s in scores if s > 0.3]) / 3.0)

    if top1 >= 0.6:
        needs_retry = False
        reason = "top1 score " + str(round(top1, 2)) + " >= 0.6"
    elif top1 >= 0.4 and avg >= 0.3:
        needs_retry = False
        reason = "top1 " + str(round(top1, 2)) + ", avg " + str(round(avg, 2)) + " acceptable"
    else:
        needs_retry = True
        reason = "low confidence: top1=" + str(round(top1, 2)) + ", avg=" + str(round(avg, 2))

    if use_llm and needs_retry:
        try:
            llm_eval = await _llm_evaluate(query, hits, top1, avg)
            return llm_eval
        except Exception as e:
            logger.debug("LLM self-eval failed, use heuristic: %s", e)

    return RetrievalEvaluation(
        confidence=min(1.0, top1),
        relevance=min(1.0, avg),
        coverage=coverage,
        needs_retry=needs_retry,
        reason=reason,
    )


async def _llm_evaluate(
    query: str,
    hits: List[Any],
    top1_score: float,
    avg_score: float,
) -> RetrievalEvaluation:
    """用 LLM 评估检索结果质量."""
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg

    top_hits = hits[:3]
    NL = chr(10)  # newline
    hits_text = NL.join(
        "[{0}] (score={1:.2f}) {2}".format(
            i + 1,
            float(getattr(h, "score", 0.0)),
            (getattr(h, "content", "") or "")[:150],
        )
        for i, h in enumerate(top_hits)
    )

    prompt = (
        "Evaluate if retrieved docs can answer the user query. "
        "Output JSON: {{\"relevance\": 0-1, \"coverage\": 0-1, "
        "\"needs_retry\": true/false, \"reason\": \"short reason\", "
        "\"suggested_rewrite\": \"rewrite or null\"}}" + NL + NL +
        "Query: " + query + NL + NL +
        "Top 3 hits:" + NL + hits_text + NL + NL + "JSON: "
    )

    model = get_model("chat")
    resp = await model(
        [UserMsg(content=prompt, role="user")],
        system_prompt="You are a retrieval quality evaluator.",
    )
    text = _extract_text(resp)

    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError("no JSON found")
        data = json.loads(m.group(0))
        return RetrievalEvaluation(
            confidence=float(data.get("relevance", top1_score)),
            relevance=float(data.get("relevance", 0.0)),
            coverage=float(data.get("coverage", 0.0)),
            needs_retry=bool(data.get("needs_retry", False)),
            reason=str(data.get("reason", "LLM evaluated")),
            suggested_rewrite=data.get("suggested_rewrite"),
        )
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logger.debug("LLM eval JSON parse failed: %s", e)
        return RetrievalEvaluation(
            confidence=top1_score,
            relevance=avg_score,
            coverage=min(1.0, len(hits) / 3.0),
            needs_retry=top1_score < 0.4,
            reason="LLM eval parse failed, fallback heuristic",
        )


def _extract_text(resp) -> str:
    if hasattr(resp, "content") and resp.content:
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text:
                text += block.text
        return text
    return str(resp)


async def self_rag_retrieve(
    query: str,
    retrieve_fn: Callable[..., Awaitable],
    tenant_id: str = "default",
    top_k: int = 3,
    max_retries: int = 2,
    confidence_threshold: float = 0.4,
) -> dict:
    """Self-RAG main entry: retrieve -> evaluate -> optional retry."""
    from app.rag.query.rewriter import rewrite as do_rewrite

    attempts = 0
    current_query = query
    rewrite_history = [query]
    last_evaluation: Optional[RetrievalEvaluation] = None
    last_result = None

    while attempts <= max_retries:
        attempts += 1
        logger.info("Self-RAG attempt %d/%d: %r", attempts, max_retries + 1, current_query[:50])

        result = await retrieve_fn(current_query, tenant_id, top_k * 2)
        hits = result.hits if hasattr(result, "hits") else result
        last_result = result

        evaluation = await evaluate_retrieval_confidence(current_query, hits)
        last_evaluation = evaluation

        if not evaluation.needs_retry or evaluation.confidence >= confidence_threshold:
            logger.info("Self-RAG: pass on attempt %d (conf=%.2f)", attempts, evaluation.confidence)
            break

        if attempts > max_retries:
            logger.info("Self-RAG: max retries, accept best")
            break

        if evaluation.suggested_rewrite:
            current_query = evaluation.suggested_rewrite
        else:
            try:
                rewritten = await do_rewrite(current_query)
                if rewritten.candidates and rewritten.candidates[0]:
                    current_query = rewritten.candidates[0]
            except Exception as e:
                logger.warning("Self-RAG rewrite failed: %s", e)
        rewrite_history.append(current_query)
        logger.info("Self-RAG: retry with %r", current_query[:50])

    return {
        "hits": last_result.hits if last_result and hasattr(last_result, "hits") else [],
        "evaluation": last_evaluation,
        "attempts": attempts,
        "rewrite_history": rewrite_history,
    }


__all__ = [
    "RetrievalEvaluation",
    "evaluate_retrieval_confidence",
    "self_rag_retrieve",
]
