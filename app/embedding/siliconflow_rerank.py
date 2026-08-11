# -*- coding: utf-8 -*-
"""硅基流动 Rerank 客户端。

调用 Rerank API（OpenAI 兼容）：
  POST {base_url}/rerank
  Body: {"model": ..., "query": ..., "documents": [...]}
  Returns: {"results": [{"index": int, "relevance_score": float}, ...]}

参考: https://docs.siliconflow.cn/cn/api-reference/rerank/create-rerank
"""
from __future__ import annotations

import logging
from typing import Any, List, Sequence

import httpx

logger = logging.getLogger(__name__)


class RerankResult:
    """Rerank 结果。"""
    def __init__(self, scores: List[float]):
        self.scores = scores


class SiliconFlowRerank:
    """硅基流动 Rerank 客户端。"""
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.siliconflow.cn/v1/rerank",
        model: str = "BAAI/bge-reranker-v2-m3",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def __call__(self, pairs: Sequence[Sequence[str]]) -> RerankResult:
        """执行 Rerank。

        Args:
            pairs: [[query, document], ...] 列表

        Returns:
            RerankResult.scores: 与 pairs 对齐的相关性分数列表
        """
        if not pairs:
            return RerankResult(scores=[])

        queries = [p[0] for p in pairs]
        documents = [p[1] for p in pairs]

        # 硅基流动 Rerank API: 一次只支持一对 (query, documents[])
        # 合并所有 docs 到一次调用，返回每个 doc 的 score
        # 如果 queries 全部相同（典型场景），合并调用
        if len(set(queries)) == 1:
            payload = {
                "model": self.model,
                "query": queries[0],
                "documents": documents,
                "return_documents": False,
                "top_n": len(documents),
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            # 构造与 documents 顺序对齐的 scores 列表
            indexed_scores = {r["index"]: r["relevance_score"] for r in data.get("results", [])}
            scores = [indexed_scores.get(i, 0.0) for i in range(len(documents))]
            return RerankResult(scores=scores)

        # 多 query 场景：逐个调用
        scores: List[float] = []
        for q, d in zip(queries, documents):
            try:
                payload = {
                    "model": self.model,
                    "query": q,
                    "documents": [d],
                    "return_documents": False,
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                s = data["results"][0]["relevance_score"] if data.get("results") else 0.0
                scores.append(s)
            except Exception as e:
                logger.warning("Rerank 单次失败: %s", e)
                scores.append(0.0)
        return RerankResult(scores=scores)
