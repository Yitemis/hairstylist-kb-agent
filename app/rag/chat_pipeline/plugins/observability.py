# -*- coding: utf-8 -*-
"""ObservabilityPlugin: 全链路决策日志 + Prometheus 指标.

职责:
  1. Prometheus: 累加 phase 维度指标 (per phase latency + decision)
  2. 决策日志: 写 rag_decision_log 表 (如果启用)
  3. 结构化日志: JSON 输出, 供 ELK / Loki 抓

输出:
  - 不改 ctx 业务字段, 只追加诊断信息 (phase_latencies 已被 runner 累加)
  - 失败也写日志 (便于故障排查)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


# Prometheus 累加函数 (延迟 import 防循环)
def _emit_prom_metrics(ctx: PipelineContext) -> None:
    """写 Prometheus phase 维度指标."""
    try:
        from app.core.metrics import (
            rag_phase_latency_seconds,
            rag_gate_decisions_total,
            rag_recall_quality_hist,
        )
        tenant_id = str(ctx.user_id) if ctx.user_id else "default"
        for phase, ms in ctx.phase_latencies.items():
            rag_phase_latency_seconds.labels(
                phase=phase, tenant_id=tenant_id,
            ).observe(ms / 1000.0)
        # gate 决策
        rag_gate_decisions_total.labels(
            decision=ctx.gate_decision, tenant_id=tenant_id,
        ).inc()
        # top1 分数分布
        if ctx.top1_score > 0:
            rag_recall_quality_hist.labels(tenant_id=tenant_id).observe(
                ctx.top1_score,
            )
    except Exception as e:
        logger.debug("Prom emit failed: %s", e)


def _save_decision_log(ctx: PipelineContext) -> None:
    """写 rag_decision_log 表 (异步, 失败不影响业务)."""
    try:
        from app.db.session import async_session_maker
        from app.db.models import RagDecisionLog
        import asyncio

        async def _do_save() -> None:
            async with async_session_maker() as session:
                log = RagDecisionLog(
                    trace_id=ctx.trace_id,
                    user_id=ctx.user_id,
                    tenant_id=str(ctx.user_id) if ctx.user_id else "default",
                    query=ctx.message[:1000],
                    # Phase 1
                    intent=ctx.intent,
                    intake_route=ctx.intake_route,
                    # Phase 2
                    rewrite_strategies=ctx.rewrite_strategies,
                    rewrite_candidates=[
                        m for m in ctx.rewrite_candidates_meta[:10]
                    ],
                    # Phase 3
                    vector_count=len(ctx.vector_candidates),
                    bm25_count=len(ctx.bm25_candidates),
                    recall_count=ctx.child_hits_count,
                    # Phase 4
                    rerank_top_n=[{
                        "parent_id": h.get("parent_id", ""),
                        "rerank_score": h.get("rerank_score", 0.0),
                    } for h in ctx.reranked_hits[:10]],
                    rerank_applied=ctx.rerank_applied,
                    # Phase 5
                    gate_decision=ctx.gate_decision,
                    gate_reason=ctx.gate_reason,
                    top1_score=ctx.top1_score,
                    # Phase 6
                    context_count=len(ctx.context_chunks),
                    context_tokens=ctx.context_tokens,
                    # Phase 7
                    answer=ctx.answer[:2000],
                    answer_tokens=ctx.answer_tokens,
                    answer_latency_ms=ctx.answer_latency_ms,
                    # Phase 8
                    validator_passed=ctx.validator_passed,
                    validator_reason=ctx.validator_reason,
                    citation_count=ctx.citation_count,
                    # Meta
                    version_tag=ctx.version_tag,
                    phase_latencies=ctx.phase_latencies,
                    error=ctx.error,
                )
                session.add(log)
                await session.commit()

        # 用 asyncio.create_task 不 await (观测不影响主链路)
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_do_save())
        except RuntimeError:
            # 没有 event loop, 同步跑 (测试场景)
            asyncio.run(_do_save())
    except Exception as e:
        logger.debug("decision_log save failed: %s", e)


def _emit_structured_log(ctx: PipelineContext) -> None:
    """结构化 JSON 日志."""
    try:
        from app.core.structured_logging import get_logger
        slog = get_logger("rag_pipeline")
        slog.info(
            "rag_pipeline_complete",
            extra={
                "trace_id": ctx.trace_id,
                "user_id": ctx.user_id,
                "intent": ctx.intent,
                "gate_decision": ctx.gate_decision,
                "top1_score": round(ctx.top1_score, 3),
                "phase_latencies_ms": ctx.phase_latencies,
                "total_ms": int(time.time() * 1000) - ctx.started_at_ms,
                "validator_passed": ctx.validator_passed,
                "error": ctx.error,
            },
        )
    except Exception as e:
        logger.debug("Structured log emit failed: %s", e)


class ObservabilityPlugin(Plugin):
    """可观测 Plugin.

    priority=100 (Pipeline 最后跑, 但 runner 已经累计了 phase_latencies)
    """

    name = "observability"
    priority = 100

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        # 1. Prometheus 指标
        _emit_prom_metrics(ctx)
        # 2. 决策日志 (DB)
        _save_decision_log(ctx)
        # 3. 结构化日志
        _emit_structured_log(ctx)
        logger.info(
            "Observability: trace_id=%s phases=%d gate=%s",
            ctx.trace_id, len(ctx.phase_latencies), ctx.gate_decision,
        )
        return ctx


__all__ = ["ObservabilityPlugin"]
