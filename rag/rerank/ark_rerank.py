# -*- coding: utf-8 -*-
"""ArkRerankModel —— 火山方舟 Rerank 模型实现。

火山方舟的 rerank 一般提供 OpenAI 风格的 HTTP 端点，请求体形如：
    { "model": "<接入点>", "query": "...", "documents": ["...", "..."] }
响应体一般形如：
    { "results": [ {"index": 0, "relevance_score": 0.98}, ... ] }

由于不同版本字段名可能略有差异，本实现对响应做了兼容解析
（relevance_score / score 均可）。

【健壮性】继承自我们在 embedding 适配器上的经验：
  - 稳健的 URL 拼接（避免重复拼接端点路径）；
  - 简单重试（应对服务端偶发 5xx 抖动）。
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

        # 稳健拼接 /rerank 端点：若已包含则不重复拼接（吸取 embedding 的教训）
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

        # 重试耗尽仍失败：抛出让上层决定是否降级
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
        # 保险起见按分数降序（多数 API 已排序，这里再确保一次）
        parsed.sort(key=lambda r: r.score, reverse=True)
        return parsed
