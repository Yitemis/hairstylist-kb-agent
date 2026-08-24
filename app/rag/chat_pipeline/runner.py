# -*- coding: utf-8 -*-
"""PluginRunner: 串联 Plugin, 执行 Pipeline.

执行模型:
    plugin_chain (按 priority 排序)
    -> 逐个调用 on_event(ctx)
    -> 任一 Plugin 抛出异常 -> 中断, 设置 ctx.error
    -> 记录每个 phase 的耗时 (Observability 用)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class PluginRunner:
    """Plugin 链执行器.

    - 持有 plugin 列表 (按 priority 排序)
    - run(ctx) 逐个执行
    - 任一插件抛异常 -> ctx.error 设置 + 中断
    - 每个 phase 耗时记到 ctx.phase_latencies
    """

    def __init__(self, plugins: Optional[List[Plugin]] = None):
        self._plugins: List[Plugin] = []
        self._counter = 0  # 用于保持插入顺序
        if plugins:
            for p in plugins:
                self.add(p)

    def add(self, plugin: Plugin) -> "PluginRunner":
        """添加 Plugin (按 priority 排序, 同 priority 按插入顺序)."""
        self._counter += 1
        # 用 (priority, _counter) 作为 sort key, 保证插入顺序
        # counter 单调递增, 不会冲突
        try:
            object.__setattr__(plugin, "_insertion_order", self._counter)
        except Exception:
            pass
        self._plugins.append(plugin)
        self._plugins.sort(
            key=lambda p: (p.priority, getattr(p, "_insertion_order", 0)),
        )
        logger.info(
            "PluginRunner: registered %s (priority=%d, enabled=%s)",
            plugin.name, plugin.priority, plugin.enabled,
        )
        return self

    @property
    def plugins(self) -> List[Plugin]:
        return list(self._plugins)

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        """顺序执行所有 Plugin, 返回最终 ctx.

        Self-RAG retry: gate=rewrite_retry + enable_self_rag 时
        从 QueryRewritePlugin 重新跑 (改 query + 重 recall + 重 gate)
        最多 self_rag_max_retries 次.

        Args:
            ctx: Pipeline 上下文 (mutated in-place)

        Returns:
            执行完所有 Plugin 后的 ctx
        """
        logger.info(
            "PluginRunner: starting trace_id=%s msg=%r user=%d self_rag=%s",
            ctx.trace_id, ctx.message[:30], ctx.user_id, ctx.enable_self_rag,
        )

        # Self-RAG retry 循环
        max_retries = getattr(ctx, "self_rag_max_retries", 2) if ctx.enable_self_rag else 0
        attempt = 0
        # 找 rewrite/rerank/gate 的 plugin index (用于 retry 时跳过已经跑过的)
        rewrite_idx = next(
            (i for i, p in enumerate(self._plugins) if p.name == "query_rewrite"),
            1,
        )

        while True:
            # 决定这次跑哪些 plugin
            if attempt == 0:
                # 第一次跑全部
                start_idx = 0
            else:
                # retry: 从 rewrite 开始 (改 query -> 重 recall -> 重 gate)
                start_idx = rewrite_idx
                logger.info(
                    "PluginRunner: Self-RAG retry attempt=%d trace_id=%s",
                    attempt, ctx.trace_id,
                )
                ctx.gate_decision = "proceed"  # reset 让 gate 重新判

            for idx in range(start_idx, len(self._plugins)):
                plugin = self._plugins[idx]
                if not plugin.enabled:
                    logger.debug("Plugin %s disabled, skip", plugin.name)
                    continue

                # Gate 拒绝后只跑 Compress/Generate/Validate/Observe (轻量)
                if ctx.gate_decision == "refuse" and plugin.name not in (
                    "compress", "generate", "answer_validator", "observability"
                ):
                    logger.debug(
                        "Plugin %s skipped (gate=refuse)", plugin.name,
                    )
                    continue

                t0 = time.time()
                try:
                    ctx = await plugin.on_event(ctx)
                except Exception as e:
                    logger.exception(
                        "Plugin %s failed: %s: %s",
                        plugin.name, type(e).__name__, e,
                    )
                    ctx.error = f"{plugin.name}: {type(e).__name__}: {e}"
                    ctx.record_phase(plugin.name, int((time.time() - t0) * 1000))
                    break
                latency_ms = int((time.time() - t0) * 1000)
                # Self-RAG: 第一次跑就记 phase, retry 时用后缀
                phase_name = (
                    plugin.name if attempt == 0
                    else f"{plugin.name}_retry{attempt}"
                )
                ctx.record_phase(phase_name, latency_ms)
                logger.debug(
                    "Plugin %s done in %dms (cum=%dms)",
                    plugin.name, latency_ms, sum(ctx.phase_latencies.values()),
                )

                # Self-RAG: 跑到 gate 时检查是否要 retry
                if plugin.name == "quality_gate" and ctx.gate_decision == "rewrite_retry":
                    if attempt < max_retries:
                        # 清空之前阶段的结果, 让 rewrite 重新生成 candidates
                        ctx.candidate_queries = []
                        ctx.vector_candidates = []
                        ctx.bm25_candidates = []
                        ctx.fused_candidates = []
                        ctx.reranked_hits = []
                        ctx.context_chunks = []
                        attempt += 1
                        logger.info(
                            "PluginRunner: Self-RAG gate=rewrite_retry, retry attempt=%d",
                            attempt,
                        )
                        break  # 跳出 for, 进入 while 重跑
                    else:
                        logger.info(
                            "PluginRunner: Self-RAG max retries reached (%d), giving up",
                            max_retries,
                        )
                        # 标记最终决定, 让后续 plugin 跑完
                        ctx.gate_decision = "proceed_with_warn"
                        ctx.gate_reason = f"max_self_rag_retries({max_retries}) " + ctx.gate_reason
                        continue

            else:
                # for 循环正常结束 (没 break)
                break

            # 检查是否要再 retry
            if attempt > max_retries:
                break

        total_ms = int(time.time() * 1000) - ctx.started_at_ms
        logger.info(
            "PluginRunner: done trace_id=%s total=%dms attempts=%d phases=%d error=%s",
            ctx.trace_id, total_ms, attempt + 1,
            len(ctx.phase_latencies), ctx.error,
        )
        return ctx


# 全局默认 runner (懒加载, 第一次 build_pipeline_chain 时初始化)
_default_runner: Optional[PluginRunner] = None


def get_default_runner() -> PluginRunner:
    """获取默认 Runner (首次调用时构建).

    Returns:
        装配好的 PluginRunner, 10 个 Plugin 按 priority 串联
    """
    global _default_runner
    if _default_runner is None:
        from app.rag.chat_pipeline.plugins.compress import CompressPlugin
        from app.rag.chat_pipeline.plugins.generate import GeneratePlugin
        from app.rag.chat_pipeline.plugins.gate import QualityGatePlugin
        from app.rag.chat_pipeline.plugins.intake import IntakePlugin
        from app.rag.chat_pipeline.plugins.observability import ObservabilityPlugin
        from app.rag.chat_pipeline.plugins.answer_validator import (
            AnswerValidatorPlugin,
        )
        from app.rag.chat_pipeline.plugins.prefilter import PrefilterPlugin
        from app.rag.chat_pipeline.plugins.recall import RecallPlugin
        from app.rag.chat_pipeline.plugins.rewrite import QueryRewritePlugin
        from app.rag.chat_pipeline.plugins.rerank import RerankPlugin

        _default_runner = PluginRunner([
            IntakePlugin(),         # priority=10
            QueryRewritePlugin(),   # priority=20
            PrefilterPlugin(),      # priority=30
            RecallPlugin(),         # priority=40
            RerankPlugin(),         # priority=50
            QualityGatePlugin(),    # priority=60
            CompressPlugin(),       # priority=70
            GeneratePlugin(),       # priority=80
            AnswerValidatorPlugin(),# priority=90
            ObservabilityPlugin(),  # priority=100
        ])
    return _default_runner


def reset_default_runner() -> None:
    """重置 (测试用)."""
    global _default_runner
    _default_runner = None


__all__ = ["PluginRunner", "get_default_runner", "reset_default_runner"]
