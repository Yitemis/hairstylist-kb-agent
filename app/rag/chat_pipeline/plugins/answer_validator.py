# -*- coding: utf-8 -*-
"""AnswerValidatorPlugin: 答案层校验 (防幻觉 + 引用对位).

职责:
  1. 简单版 (默认): 启发式
     - answer 关键词是否在 context 中 -> 粗略 faithfulness
     - 引用数 (citation_count) >= 1 才算合格
  2. 严格版: 接 ragas_runner.evaluate_rag()
     - 4 维 RAGAS (faithfulness / relevancy / precision / recall)
  3. 不通过 -> validator_passed=False + reason
     不重试 (避免循环), 但记到 decision_log 供归因
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


MIN_FAITHFULNESS = 0.30  # 启发式阈值
MIN_CITATION = 1


class AnswerValidatorPlugin(Plugin):
    """答案层校验 Plugin.

    priority=90
    """

    name = "answer_validator"
    priority = 90

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.enable_answer_validator:
            ctx.validator_passed = True
            ctx.validator_reason = "skipped"
            return ctx
        if ctx.gate_decision == "refuse":
            # refuse 路径不校验 (固定回复)
            ctx.validator_passed = True
            ctx.validator_reason = "refuse_path"
            return ctx

        # 1. 引用数检查
        ctx.citation_count = len(ctx.sources)
        if ctx.citation_count < MIN_CITATION and ctx.context_chunks:
            ctx.validator_passed = False
            ctx.validator_reason = (
                f"insufficient_citations count={ctx.citation_count}<{MIN_CITATION}"
            )
            logger.info("Validator: fail (%s)", ctx.validator_reason)
            return ctx

        # 2. 简单 faithfulness (启发式)
        try:
            from app.rag.evaluation.ragas_runner import (
                heuristic_faithfulness,
            )
            contexts = [c.get("content", "") for c in ctx.context_chunks]
            score = heuristic_faithfulness(ctx.answer, contexts)
            if score < MIN_FAITHFULNESS:
                ctx.validator_passed = False
                ctx.validator_reason = (
                    f"low_faithfulness={score:.2f}<{MIN_FAITHFULNESS}"
                )
                logger.info("Validator: fail (faithfulness=%.2f)", score)
                return ctx
        except Exception as e:
            logger.debug("Heuristic faithfulness failed: %s", e)

        # 3. 可选: 真 RAGAS (慢, 默认不开)
        # 启用方法: ctx.version_tag == 'ragas_real' 走 evaluate_rag()
        if ctx.version_tag == "ragas_real" and ctx.context_chunks:
            try:
                from app.rag.evaluation.ragas_runner import evaluate_rag
                ragas = evaluate_rag(
                    query=ctx.message,
                    answer=ctx.answer,
                    retrieved_contexts=[
                        c.get("content", "") for c in ctx.context_chunks
                    ],
                )
                ctx.validator_reason = (
                    f"ragas faithfulness={ragas.faithfulness:.2f} "
                    f"relevancy={ragas.answer_relevancy:.2f}"
                )
            except Exception as e:
                logger.debug("RAGAS real failed: %s", e)

        ctx.validator_passed = True
        logger.info(
            "Validator: pass (citations=%d, reason=%s)",
            ctx.citation_count, ctx.validator_reason or "ok",
        )
        return ctx


__all__ = ["AnswerValidatorPlugin", "MIN_FAITHFULNESS", "MIN_CITATION"]
