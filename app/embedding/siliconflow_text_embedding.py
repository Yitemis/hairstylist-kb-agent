# -*- coding: utf-8 -*-
"""硅基流动纯文本 embedding 适配器（OpenAI 兼容）。

支持的模型：
- BAAI/bge-large-zh-v1.5 (1024 dim, 中文)
- BAAI/bge-large-en-v1.5 (1024 dim, 英文)
- text-embedding-ada-002 (1536 dim, OpenAI 兼容)

对比 ArkVisionEmbeddingModel：
- 纯文本（更便宜，更快）
- 不支持图片（只接受 text）
- OpenAI 兼容协议（更通用）
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agentscope.credential import CredentialBase
from agentscope.embedding import EmbeddingModelBase
from agentscope.embedding._embedding_response import EmbeddingResponse
from agentscope.embedding._embedding_usage import EmbeddingUsage
from agentscope.message import TextBlock

import httpx

logger = logging.getLogger(__name__)


class SiliconFlowTextEmbedding(EmbeddingModelBase[str | TextBlock]):
    """硅基流动 OpenAI 兼容纯文本 embedding。

    与 ArkVisionEmbeddingModel 的区别：
    - 仅支持 TextBlock（不支持 DataBlock/图片）
    - 端点是标准 /v1/embeddings（非 multimodal）
    - 价格更便宜（BAAI 系列免费/低价）
    """

    _BATCH_SIZE = 32  # 硅基流动支持批量

    def __init__(
        self,
        credential: CredentialBase,
        model: str,
        dimensions: int | None = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        context_size: int = 8192,
        parameters: Any = None,
    ) -> None:
        # base __init__ requires credential, model, dimensions, parameters, context_size, batch_size, max_retries, retry_delay
        # But base uses these for our own model - we override _call_api
        # Pass our batch_size (32) and our max_retries
        from agentscope.embedding._embedding_usage import EmbeddingUsage as _EU
        super().__init__(
            credential=credential,
            model=model,
            dimensions=dimensions,
            parameters=parameters,
            context_size=context_size,
            batch_size=self._BATCH_SIZE,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        self._api_key = credential.api_key
        # base_url 通常是 https://api.siliconflow.cn/v1
        base = (credential.base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        self._full_url = f"{base}/embeddings"
        self._model = model
        self._dimensions = dimensions
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self.supports_multimodal = False
        logger.info(f"SiliconFlowTextEmbedding init: model={model}, url={self._full_url}")

    async def _call_api(self, inputs: list[str]) -> EmbeddingResponse:
        """调用硅基流动 embedding API。"""
        if not inputs:
            return EmbeddingResponse(embeddings=[], usage=EmbeddingUsage())

        # 纯文本：只取 TextBlock 的 text（如果有非 TextBlock，跳过或报错）
        texts = [t if isinstance(t, str) else str(t) for t in inputs]

        payload = {
            "model": self._model,
            "input": texts,
        }
        if self._dimensions:
            payload["dimensions"] = self._dimensions

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(self._full_url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"硅基流动 embedding API 错误: {resp.status_code} {resp.text[:300]}"
                        )
                    data = resp.json()
                # 解析 OpenAI 格式
                embeddings = [item["embedding"] for item in data.get("data", [])]
                usage_data = data.get("usage", {})
                usage = EmbeddingUsage(
                    input_tokens=usage_data.get("prompt_tokens", 0),
                    output_tokens=0,
                )
                return EmbeddingResponse(embeddings=embeddings, usage=usage)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    import asyncio as _aio
                    await _aio.sleep(self._retry_delay)
                continue
        raise RuntimeError(f"SiliconFlowTextEmbedding 失败: {last_error}")
