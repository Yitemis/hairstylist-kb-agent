# -*- coding: utf-8 -*-
"""QualityGatePlugin: 3 层 Gate, 失败 -> 降级/拒答.

Layer 1: 数据质量 (有候选吗)
  - candidates 空 -> refuse (no_candidates)

Layer 2: 检索质量 (top1 + 平均分)
  - top1 < HARD_REFUSE   -> refuse (几乎全是噪声)
  - top1 < SOFT_REFUSE   -> proceed_with_warn (低置信度, 仍放行)
  - 其他 -> proceed

Layer 3: 业务约束
  - 全部走 Prefilter 阶段, 这里只做最后一道兜底 (permissive)
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


# Gate 阈值. BGE rerank 对英文-英文匹配给分偏低 (0.0001-0.78),
# 阈值按分档处理: HARD 拒答, SOFT 警告但放行
HARD_REFUSE = 0.0001
SOFT_REFUSE = 0.001
AVG_NOISE = 0.3


class QualityGatePlugin(Plugin):
    """3 层 Quality Gate Plugin.

    priority=60
    """

    name = "quality_gate"
    priority = 60

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        hits = ctx.reranked_hits or ctx.fused_candidates

        # Layer 1: 数据质量
        if not hits:
            ctx.gate_decision = "refuse"
            ctx.gate_reason = "no_candidates"
            logger.info("Gate: refuse (no_candidates)")
            return ctx

        # Layer 2: 检索质量
        scores = [
            float(h.get("rerank_score", h.get("normalized_score", h.get("score", 0.0))) or 0.0)
            for h in hits
        ]
        top1 = max(scores) if scores else 0.0
        avg = sum(scores) / len(scores) if scores else 0.0
        ctx.top1_score = top1
        ctx.avg_score = avg

        if top1 < HARD_REFUSE:
            # 极低置信度, 几乎全是噪声, 拒答
            ctx.gate_decision = "refuse"
            ctx.gate_reason = f"hard_refuse top1={top1:.4f}<{HARD_REFUSE}"
            logger.info("Gate: refuse (hard, top1=%.4f)", top1)
            return ctx

        if top1 < SOFT_REFUSE:
            # 低置信度, 仍放行但标 warn (让 LLM 用 LTM + 训练知识兜底)
            ctx.gate_decision = "proceed_with_warn"
            ctx.gate_reason = f"warn low_confidence top1={top1:.4f}<{SOFT_REFUSE}"
            logger.info("Gate: proceed_with_warn (top1=%.4f)", top1)
            return ctx

        # 其他情况: top1 已经是信号最强的那条, 直接 proceed
        # Layer 3: 业务约束 (Prefilter 已处理, 这里只兜底)
        ctx.gate_decision = "proceed"
        ctx.gate_reason = f"ok top1={top1:.4f} avg={avg:.4f}"
        logger.info("Gate: proceed (top1=%.4f avg=%.4f)", top1, avg)
        return ctx


__all__ = ["QualityGatePlugin", "HARD_REFUSE", "SOFT_REFUSE", "TOP1_NOISE", "AVG_NOISE"]
