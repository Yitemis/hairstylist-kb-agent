# -*- coding: utf-8 -*-
"""ArkVisionEmbeddingModel —— 火山方舟 doubao-embedding-vision 适配器。

【框架原理】
继承 EmbeddingModelBase 只需实现一个核心方法 _call_api(inputs) -> EmbeddingResponse。
框架的 __call__ 已经帮你做好了：
  1. 把 TextBlock 自动解包为 .text 字符串
  2. 按 batch_size 分批
  3. 跨批次并发调用 asyncio.gather
  4. 自动重试（可重试异常）
  5. 合并结果

我们只需要告诉框架三件事：
  - batch_size=1（因为火山 multimodal 端点每次只接受一条输入）
  - 如何把 inputs 序列化成火山要求的请求格式
  - 如何从火山响应中提取 embedding 向量
"""
import json
from datetime import datetime
from typing import Any

from agentscope.credential import CredentialBase
from agentscope.embedding import EmbeddingModelBase
from agentscope.embedding._embedding_response import EmbeddingResponse
from agentscope.embedding._embedding_usage import EmbeddingUsage
from agentscope.message import DataBlock, TextBlock, Base64Source, URLSource

import httpx


# 火山 multimodal embedding 端点
# 相较于标准 /embeddings 端点，其请求格式为 input 数组，每个元素含 type/text 或 type/image_url 字段
_MULTIMODAL_ENDPOINT = "/embeddings/multimodal"


class ArkVisionEmbeddingModel(EmbeddingModelBase[str | TextBlock | DataBlock]):
    """火山方舟 doubao-embedding-vision 多模态嵌入模型适配器。

    支持纯文本和图片输入。图片支持 Base64 编码和 URL 两种方式。
    """

    # 火山 multimodal 端点每次只接受一条输入，batch_size 固定为 1
    # 框架的 __call__ 会自动并发处理多条输入
    _BATCH_SIZE = 1

    def __init__(
        self,
        credential: CredentialBase,
        model: str,
        dimensions: int | None,
        parameters: "ArkVisionEmbeddingModel.Parameters | None" = None,
        context_size: int = 8192,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        endpoint: str | None = None,
    ) -> None:
        """初始化火山方舟 embedding 模型。

        Args:
            credential: 包含 api_key 和 base_url 的凭证对象。
            model: 模型接入点 ID（ep-xxxxx）。
            dimensions: 输出向量维度（doubao-embedding-vision 为 2048）。
            parameters: 模型参数（当前为空）。
            context_size: 单条输入最大 token 数。
            max_retries: 重试次数。
            retry_delay: 重试间隔（秒）。
            endpoint: 自定义端点路径，默认使用 /embeddings/multimodal。
        """
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
        self.api_key = credential.api_key.get_secret_value()
        base = credential.base_url.rstrip("/")

        # 稳健地拼接端点：
        # - 若 .env 里的 base_url 已经是完整的 multimodal 端点
        #   （如 .../api/v3/embeddings/multimodal），直接使用，避免重复拼接；
        # - 否则在其后补上 /embeddings/multimodal。
        # 这样无论用户在 .env 里填 base 根路径还是完整端点都能正确工作。
        chosen_endpoint = endpoint or _MULTIMODAL_ENDPOINT
        if base.endswith(chosen_endpoint):
            self._full_url = base
        else:
            self._full_url = f"{base}{chosen_endpoint}"

        # 多模态模型标记为 True，让 KnowledgeBase.search 知道可以传入 DataBlock
        self.supports_multimodal = True

    @classmethod
    def _get_retryable_exceptions(cls) -> tuple[type[Exception], ...]:
        """声明可重试异常。

        火山方舟偶发 500 InternalServiceError（其提示信息本身就是
        "Please retry later"），属于服务端临时抖动。我们把 RuntimeError
        纳入可重试范围——_call_api 在非 200 响应时抛出 RuntimeError，
        框架的重试机制（max_retries + retry_delay）会自动重试。
        """
        return (RuntimeError,)

    # ------------------------------------------------------------------
    # 核心方法：实现单条输入的 API 调用
    # ------------------------------------------------------------------

    async def _call_api(
        self,
        inputs: list[str | DataBlock],
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """调用火山方舟 multimodal embedding API。

        Args:
            inputs: 长度为 1 的列表（batch_size=1），元素为 str 或 DataBlock。
            **kwargs: 额外参数（透传给 API）。

        Returns:
            EmbeddingResponse: 包含一个 embedding 向量的响应。

        Raises:
            ValueError: 当 inputs 为空或包含不支持的类型时。
        """
        if not inputs:
            return EmbeddingResponse(
                embeddings=[],
                usage=EmbeddingUsage(tokens=0, time=0),
            )

        # 格式化输入为火山要求的格式
        formatted = self._format_inputs(inputs)

        # 构造请求
        url = self._full_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": formatted,
            **kwargs,
        }

        start_time = datetime.now()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)

        elapsed = (datetime.now() - start_time).total_seconds()

        if response.status_code != 200:
            raise RuntimeError(
                f"火山方舟 embedding API 错误: {response.status_code} "
                f"{response.text[:500]}",
            )

        result = response.json()

        # 火山 multimodal 端点返回格式：
        # { "data": { "embedding": [...], "object": "embedding" },
        #   "usage": { "prompt_tokens": ..., "total_tokens": ... } }
        embedding = result["data"]["embedding"]

        # 计算 token 消耗
        usage_info = result.get("usage", {})
        total_tokens = usage_info.get("total_tokens", 0)

        return EmbeddingResponse(
            embeddings=[embedding],
            usage=EmbeddingUsage(
                tokens=total_tokens,
                time=elapsed,
            ),
        )

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _format_inputs(
        inputs: list[str | DataBlock],
    ) -> list[dict[str, Any]]:
        """将 inputs 转换为火山方舟要求的格式。

        火山 multimodal 端点 input 格式：
        - 文本: {"type": "text", "text": "你好"}
        - 图片(base64): {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        - 图片(URL):  {"type": "image_url", "image_url": {"url": "https://..."}}

        Args:
            inputs: 输入列表，元素为 str 或 DataBlock。

        Returns:
            list[dict]: 格式化后的 input 数组。
        """
        formatted = []
        for item in inputs:
            if isinstance(item, str):
                formatted.append({"type": "text", "text": item})
            elif isinstance(item, DataBlock):
                formatted.append(ArkVisionEmbeddingModel._format_data_block(item))
            else:
                raise ValueError(
                    f"不支持的输入类型: {type(item).__name__}，"
                    f"仅支持 str 和 DataBlock。",
                )
        return formatted

    @staticmethod
    def _format_data_block(block: DataBlock) -> dict[str, Any]:
        """将 DataBlock 转换为火山 multimodal 端点要求的图片格式。

        Args:
            block: DataBlock 实例，source 可为 Base64Source 或 URLSource。

        Returns:
            dict: 格式如 {"type": "image_url", "image_url": {"url": "..."}}。

        Raises:
            ValueError: 当 media_type 不是图片类型时。
        """
        source = block.source
        media_type = source.media_type

        if not media_type.startswith("image/"):
            raise ValueError(
                f"火山 multimodal embedding 仅支持图片类型，"
                f"收到 {media_type!r}。",
            )

        if isinstance(source, Base64Source):
            url = f"data:{media_type};base64,{source.data}"
        elif isinstance(source, URLSource):
            url = str(source.url)
        else:
            raise ValueError(
                f"不支持的 DataBlock source 类型: {type(source).__name__}",
            )

        return {"type": "image_url", "image_url": {"url": url}}