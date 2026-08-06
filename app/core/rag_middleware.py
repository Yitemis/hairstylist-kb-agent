# -*- coding: utf-8 -*-
"""RAG Middleware：自动在 onReasoning 阶段注入 RAG 知识。

借鉴 AgentScope 2.0 的 RAGMiddleware 设计：
- onReasoning 时自动触发
- 用 LLM 改写 query（Query 改写）
- 向量库检索
- 注入 HintBlock 到 system prompt

优势：所有 Agent 自动具备 RAG 能力，无需在每个工具调用里手动加。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .middleware import MiddlewareContext
from .metrics import rag_retrievals_total

logger = logging.getLogger(__name__)


class RAGMiddleware:
    """RAG 自动注入中间件。

    在 chat 流程的 LLM 调用之前，自动：
    1. 用 LLM 改写用户 query（加领域关键词）
    2. 调 search_hair_knowledge 检索
    3. 把检索结果拼到 system prompt（HintBlock 格式）
    """

    def __init__(self, top_k: int = 3, score_threshold: float = 0.5) -> None:
        self.top_k = top_k
        self.score_threshold = score_threshold

    async def on_reasoning(self, ctx: MiddlewareContext, next_fn, message: str) -> Any:
        """拦截推理阶段，注入 RAG 结果。"""
        # 1. Query 改写（加领域关键词）
        rewritten_query = await self._rewrite_query(message)
        logger.debug("RAG query rewrite: %s -> %s", message[:30], rewritten_query[:30])

        # 2. 向量检索
        from app.rag.v2_engine import retrieve, index_document
        try:
            t0 = time.time()
            result = await retrieve(
                query=rewritten_query,
                tenant_id="default",
                top_k=self.top_k,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            logger.info(
                "RAG retrieval: query=%s hits=%d elapsed=%dms",
                rewritten_query[:30], len(result.hits), elapsed_ms,
            )
            rag_retrievals_total.labels(tenant_id="default", result="success").inc()
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            rag_retrievals_total.labels(tenant_id="default", result="error").inc()
            return await next_fn()

        # 3. 注入 HintBlock 到 ctx
        if result.hits:
            hint_text = self._build_hint_text(result.hits)
            ctx.metadata["rag_hint"] = hint_text
            ctx.metadata["rag_hits_count"] = len(result.hits)
        else:
            ctx.metadata["rag_hint"] = ""

        return await next_fn()

    async def _rewrite_query(self, query: str) -> str:
        """用 LLM 改写 query（简化版：直接加领域词）。"""
        # 简单实现：直接加"美发"领域词
        # 高级实现：调 LLM 重写（避免 1 次额外 LLM 调用）
        if "美发" in query or "烫" in query or "染" in query or "剪" in query:
            return query
        return f"{query} 美发 专业知识"

    def _build_hint_text(self, hits) -> str:
        """构建 HintBlock 文本。"""
        lines = ["【知识库检索结果】"]
        for i, hit in enumerate(hits, 1):
            if hit.score < self.score_threshold:
                continue
            source = getattr(hit, "source", "unknown")
            content = getattr(hit, "content", "")[:300]
            lines.append(f"\n[{i}] 来源：{source}（分数: {hit.score:.2f}）\n{content}")
        return "\n".join(lines)


# 工厂
def get_rag_middleware() -> RAGMiddleware:
    return RAGMiddleware(top_k=3, score_threshold=0.5)
