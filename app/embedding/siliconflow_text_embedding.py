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
        # SecretStr 兼容: pydantic 会把 str 当 SecretStr, f-string 会 mask
        # 必须调用 .get_secret_value() 拿真实 key
        api_key = credential.api_key
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        self._api_key = api_key
        # base_url 通常是 https://api.siliconflow.cn/v1
        # 但 .env 也可能写 https://api.siliconflow.cn/v1/embeddings (避免双拼)
        base_url = credential.base_url
        if hasattr(base_url, "get_secret_value"):
            base_url = base_url.get_secret_value()
        base = (base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        if base.endswith("/embeddings"):
            self._full_url = base
        else:
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
        # BAAI/bge-large-zh-v1.5 不支持 dimensions 参数 (会 400)
        # 切换模型时记得测试兼容性
        if self._dimensions and "bge-large" not in self._model.lower():
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
                # EmbeddingUsage signature: (time, tokens, type)
                usage = EmbeddingUsage(
                    time=0.0,
                    tokens=usage_data.get("prompt_tokens", 0),
                    type="embedding",
                )
                return EmbeddingResponse(embeddings=embeddings, usage=usage)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    import asyncio as _aio
                    await _aio.sleep(self._retry_delay)
                continue
        raise RuntimeError(f"SiliconFlowTextEmbedding 失败: {last_error}")
