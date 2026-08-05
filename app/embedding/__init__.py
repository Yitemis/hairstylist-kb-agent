# -*- coding: utf-8 -*-
"""自定义 Embedding 适配器。"""
from .ark_vision_embedding import ArkVisionEmbeddingModel
from .siliconflow_text_embedding import SiliconFlowTextEmbedding
from .router import Capability, get_model_router, get_endpoint

# 全局单例，避免重复初始化
_embedding_model: ArkVisionEmbeddingModel | None = None
_rerank_model = None


def build_embedding_model(capability: str = "text_embedding"):
    """基于 capability 构建 embedding 模型（ModelRouter 路由）。

    Args:
        capability: 'text_embedding' (硅基流动) | 'mm_embedding' (火山方舟)

    Returns:
        EmbeddingModelBase 实例（多模态或纯文本）

    Raises:
        RuntimeError: capability 端点不可用（如 mm_embedding 欠费）
    """
    from agentscope.credential import OpenAICredential

    cap = Capability(capability) if isinstance(capability, str) else capability
    endpoint = get_endpoint(cap)
    if endpoint is None:
        raise RuntimeError(
            f"模型能力 {capability} 不可用（未配置或被禁用）。"
            f"当前可用: {[c.value for c in get_model_router().list_capabilities()]}"
        )
    credential = OpenAICredential(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
    )
    if cap == Capability.TEXT_EMBEDDING:
        return SiliconFlowTextEmbedding(
            credential=credential,
            model=endpoint.model,
            dimensions=endpoint.dimensions,
        )
    elif cap == Capability.MM_EMBEDDING:
        return ArkVisionEmbeddingModel(
            credential=credential,
            model=endpoint.model,
            dimensions=endpoint.dimensions,
        )
    else:
        raise RuntimeError(f"不支持的 capability: {capability}")


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
