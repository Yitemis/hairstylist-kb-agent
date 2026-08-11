# -*- coding: utf-8 -*-
"""模型路由：按 capability 选择合适的模型。

能力维度：
- text_embedding:  纯文本向量（硅基流动 BAAI, 便宜快速）
- mm_embedding:    多模态向量（火山方舟, 支持图片）
- chat:            纯文本对话（火山方舟 coding plan）
- mm_chat:         多模态对话（火山方舟, 支持图片）
- rerank:          重排（硅基流动 BAAI, 免费）

- 业务按 capability 调用，不关心具体模型
- 路由表配置在 .env，可热切换
- 支持 fallback（主模型挂了用次选）
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """模型能力维度。"""
    TEXT_EMBEDDING = "text_embedding"
    MM_EMBEDDING = "mm_embedding"
    CHAT = "chat"
    MM_CHAT = "mm_chat"
    RERANK = "rerank"


@dataclass
class ModelEndpoint:
    """单个模型端点配置。"""
    capability: Capability
    provider: str           # "ark" / "siliconflow" / "openai"
    api_key: str
    base_url: str
    model: str
    dimensions: Optional[int] = None
    enabled: bool = True    # False 时跳过（用于欠费场景）


class ModelRouter:
    """按能力路由到对应模型。"""

    def __init__(self):
        self._endpoints: dict[Capability, ModelEndpoint] = {}
        self._load_from_env()

    def _load_from_env(self):
        """从环境变量加载所有端点。"""
        # 1. Chat（火山方舟 coding plan）
        chat_key = os.environ.get("CHAT_API_KEY", "")
        if chat_key:
            self._endpoints[Capability.CHAT] = ModelEndpoint(
                capability=Capability.CHAT,
                provider="ark",
                api_key=chat_key,
                base_url=os.environ.get("CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                model=os.environ.get("CHAT_MODEL", "ark-code-latest"),
            )
        # MM_CHAT 复用 CHAT（同火山方舟）
        if Capability.CHAT in self._endpoints:
            self._endpoints[Capability.MM_CHAT] = ModelEndpoint(
                capability=Capability.MM_CHAT,
                provider="ark",
                api_key=self._endpoints[Capability.CHAT].api_key,
                base_url=self._endpoints[Capability.CHAT].base_url,
                model=self._endpoints[Capability.CHAT].model,
            )

        # 2. Text embedding（硅基流动 BAAI - 便宜快速）
        text_key = os.environ.get("TEXT_EMBEDDING_API_KEY", "")
        if text_key:
            self._endpoints[Capability.TEXT_EMBEDDING] = ModelEndpoint(
                capability=Capability.TEXT_EMBEDDING,
                provider="siliconflow",
                api_key=text_key,
                base_url=os.environ.get("TEXT_EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1"),
                model=os.environ.get("TEXT_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5"),
                dimensions=int(os.environ.get("TEXT_EMBEDDING_DIMENSIONS", "1024")),
            )

        # 3. Multimodal embedding（火山方舟 - 欠费时禁用）
        mm_key = os.environ.get("EMBEDDING_API_KEY", "").strip('"')
        if mm_key:
            self._endpoints[Capability.MM_EMBEDDING] = ModelEndpoint(
                capability=Capability.MM_EMBEDDING,
                provider="ark",
                api_key=mm_key,
                base_url=os.environ.get("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"),
                model=os.environ.get("EMBEDDING_MODEL", "ep-xxx"),
                dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "2048")),
                enabled=os.environ.get("MM_EMBEDDING_ENABLED", "1") == "1",
            )

        # 4. Rerank（硅基流动 - 免费）
        rk_key = os.environ.get("RERANK_API_KEY", "")
        if rk_key:
            self._endpoints[Capability.RERANK] = ModelEndpoint(
                capability=Capability.RERANK,
                provider="siliconflow",
                api_key=rk_key,
                base_url=os.environ.get("RERANK_BASE_URL", "https://api.siliconflow.cn/v1/rerank"),
                model=os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            )

    def get_endpoint(self, capability: Capability) -> Optional[ModelEndpoint]:
        """获取端点（不存在或 disabled 返回 None）。"""
        ep = self._endpoints.get(capability)
        if ep is None or not ep.enabled:
            return None
        return ep

    def list_capabilities(self) -> list[Capability]:
        return [c for c, ep in self._endpoints.items() if ep.enabled]

    def disable(self, capability: Capability):
        """运行时禁用某能力（如欠费）。"""
        if capability in self._endpoints:
            self._endpoints[capability].enabled = False
            logger.warning("ModelRouter: %s disabled", capability)

    def enable(self, capability: Capability):
        if capability in self._endpoints:
            self._endpoints[capability].enabled = True
            logger.info("ModelRouter: %s enabled", capability)

    def summary(self) -> dict:
        return {
            c.value: {
                "provider": ep.provider,
                "model": ep.model,
                "enabled": ep.enabled,
            }
            for c, ep in self._endpoints.items()
        }


# 全局单例
_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def get_endpoint(capability: Capability) -> Optional[ModelEndpoint]:
    return get_model_router().get_endpoint(capability)
