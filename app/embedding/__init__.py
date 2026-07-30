# -*- coding: utf-8 -*-
"""自定义 Embedding 适配器。"""
from .ark_vision_embedding import ArkVisionEmbeddingModel

# 全局单例，避免重复初始化
_embedding_model: ArkVisionEmbeddingModel | None = None


def build_embedding_model() -> ArkVisionEmbeddingModel:
    """基于配置构建火山方舟 vision embedding 模型实例。

    Returns:
        ArkVisionEmbeddingModel: 可传给 KnowledgeBase 的嵌入模型。
    """
    from agentscope.credential import OpenAICredential

    from ..core.config import embedding_config

    credential = OpenAICredential(
        api_key=embedding_config.api_key,
        base_url=embedding_config.base_url,
    )
    return ArkVisionEmbeddingModel(
        credential=credential,
        model=embedding_config.model,
        dimensions=embedding_config.dimensions,
    )


__all__ = ["ArkVisionEmbeddingModel", "build_embedding_model"]
