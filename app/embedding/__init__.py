# -*- coding: utf-8 -*-
"""自定义 Embedding 适配器。"""
from .ark_vision_embedding import ArkVisionEmbeddingModel

# 全局单例，避免重复初始化
_embedding_model: ArkVisionEmbeddingModel | None = None
_rerank_model = None


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


def build_rerank_model():
    """构建 Rerank 模型（基于火山方舟 Rerank API）。

    火山方舟提供 gte-rerank 等模型，OpenAI 兼容协议：
        POST {base_url}/rerank
        Body: {"model": "gte-rerank", "input": {"query": ..., "documents": [...]}}
    """
    global _rerank_model
    if _rerank_model is None:
        from agentscope.model import DashScopeRerankModel
        from ..core.config import rerank_config
        if not rerank_config.is_valid:
            return None
        from agentscope.credential import DashScopeCredential

        credential = DashScopeCredential(api_key=rerank_config.api_key)
        _rerank_model = DashScopeRerankModel(
            credential=credential,
            model=rerank_config.model,
        )
    return _rerank_model


__all__ = ["ArkVisionEmbeddingModel", "build_embedding_model", "build_rerank_model"]
