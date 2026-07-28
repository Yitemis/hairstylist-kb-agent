# -*- coding: utf-8 -*-
"""火山方舟 Rerank 模型实现。

火山方舟的 Rerank 提供 HTTP 端点，请求体形如::

    {"model": "<接入点>", "query": "...", "documents": ["...", "..."]}

响应体形如::

    {"results": [{"index": 0, "relevance_score": 0.98}, ...]}

不同版本的响应字段名可能不同，此实现对 ``relevance_score`` 与 ``score``
两种命名均做兼容解析，并在网络抖动时进行有限次重试。
"""
import asyncio

import httpx

from .base import RerankModelBase, RerankResult


class ArkRerankModel(RerankModelBase):
    """火山方舟 Rerank 模型。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_retries: int = 3,
        retry_delay: float = 1.5,
        timeout: float = 30.0,
    ) -> None:
        """初始化火山 rerank 模型。

        Args:
            api_key: 火山方舟 API Key。
            base_url: rerank 端点 base_url（可为根路径或完整 /rerank 端点）。
            model: rerank 模型接入点 ID / 名称。
            max_retries: 失败重试次数。
            retry_delay: 重试间隔（秒）。
            timeout: 单次请求超时（秒）。
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

        # 拼接 /rerank 端点：若 base_url 已包含则不重复拼接
        base = base_url.rstrip("/")
        if base.endswith("/rerank"):
            self._url = base
        else:
            self._url = f"{base}/rerank"

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """调用火山 rerank API 对文档重排。

        Args:
            query: 查询文本。
            documents: 候选文档列表。
            top_n: 返回前 N 个（None 返回全部）。

        Returns:
            list[RerankResult]: 按分数降序。
        """
        if not documents:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self._url,
                        headers=headers,
                        json=payload,
                    )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"火山 rerank API 错误: {resp.status_code} "
                        f"{resp.text[:300]}",
                    )
                return self._parse_response(resp.json())
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)

        # 重试耗尽仍失败：抛出异常，由上层决定是否降级
        raise RuntimeError(f"火山 rerank 调用失败: {last_error}")

    @staticmethod
    def _parse_response(data: dict) -> list[RerankResult]:
        """兼容解析 rerank 响应。

        兼容两类字段命名：relevance_score / score。
        """
        results = data.get("results", [])
        parsed: list[RerankResult] = []
        for item in results:
            score = item.get("relevance_score")
            if score is None:
                score = item.get("score", 0.0)
            parsed.append(
                RerankResult(index=item["index"], score=float(score)),
            )
        # 多数 API 已按分数排序，此处再确保一次降序
        parsed.sort(key=lambda r: r.score, reverse=True)
        return parsed
