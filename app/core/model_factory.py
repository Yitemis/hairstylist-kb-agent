# -*- coding: utf-8 -*-
"""模型工厂：基于 AgentScope 2.0 原生 OpenAIChatModel 的接入层。

AgentScope 2.0 中对话模型使用 OpenAIChatModel（OpenAI 兼容协议），
通过 OpenAICredential 注入鉴权信息。火山方舟 / DeepSeek / 月之暗面
等只要提供 OpenAI 兼容 endpoint 即可复用。
"""
from __future__ import annotations

import logging
from typing import Any

from agentscope.credential import OpenAICredential
from agentscope.model import ChatModelBase, OpenAIChatModel

from app.core.config import model_configs

logger = logging.getLogger(__name__)


class ChatModel(OpenAIChatModel):
    """对话模型：基于 AgentScope 2.0 OpenAIChatModel。

    原生提供：流式输出、函数调用、token 统计、失败重试。
    本层扩展：审计日志钩子位（后续可加）。
    """

    def __init__(self, config_name: str = "chat") -> None:
        cfg = model_configs[config_name]
        if not cfg.is_valid:
            raise ValueError(
                f"对话模型配置不完整（{config_name}），"
                "请检查 .env 中的 *_API_KEY / *_BASE_URL / *_MODEL",
            )
        credential = OpenAICredential(
            api_key=cfg.api_key,
            base_url=cfg.base_url or None,
        )
        super().__init__(
            credential=credential,
            model=cfg.model,
            stream=cfg.stream,
            max_retries=cfg.max_retries,
            retry_delay=1.0,
        )
        self._config_name = config_name


# ------------------------------------------------------------------
# 模型注册中心
# ------------------------------------------------------------------

_MODEL_REGISTRY: dict[str, type[ChatModelBase]] = {
    "chat": ChatModel,
}

_model_instances: dict[str, ChatModelBase] = {}


def get_model(model_type: str = "chat") -> ChatModelBase:
    """获取模型实例（单例，懒加载）。

    Args:
        model_type: 模型类型（chat / embedding / rerank）。

    Returns:
        配置好的 ChatModelBase 实例。
    """
    if model_type not in _model_instances:
        if model_type not in _MODEL_REGISTRY:
            raise ValueError(f"未知模型类型: {model_type}")
        _model_instances[model_type] = _MODEL_REGISTRY[model_type]()
    return _model_instances[model_type]


def reload_models() -> None:
    """热重载所有模型实例（配置变更后调用）。"""
    global _model_instances
    _model_instances = {}
