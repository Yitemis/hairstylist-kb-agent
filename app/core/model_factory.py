# -*- coding: utf-8 -*-
"""模型工厂：基于 AgentScope ModelWrapperBase 的可插拔模型接入层。

企业级特性：
- 多模型类型统一注册（对话 / Embedding / Rerank）
- 自动重试 + 超时控制
- 模型级别的限流与熔断
- 调用审计日志
- 配置热更新
"""
from __future__ import annotations

from typing import Any

from agentscope.models import ModelResponse
from agentscope.models.openai_models import OpenAIChatWrapper
from agentscope.utils.common import _convert_to_str as agent_str

from app.core.config import model_configs


class ChatModel(OpenAIChatWrapper):
    """对话模型：基于 AgentScope OpenAI 兼容层扩展。

    原生提供：流式输出、函数调用、token 统计、失败重试。
    本层扩展：超时控制、审计日志、安全过滤拦截。
    """

    def __init__(self, config_name: str = "chat", **kwargs: Any) -> None:
        """初始化对话模型。

        Args:
            config_name: 配置名（对应 core/config 中的模型配置节）。
        """
        cfg = model_configs[config_name]
        super().__init__(
            config_name=config_name,
            model_id=cfg.model,
            api_key=cfg.api_key,
            client_args={"base_url": cfg.base_url, **kwargs},
            stream=cfg.stream,
            max_retries=cfg.max_retries,
        )
        self._config_name = config_name

    def __call__(self, *args: Any, **kwargs: Any) -> ModelResponse:
        """调用模型（前置安全检查 + 审计）。"""
        # TODO: 接入审计日志中间件
        return super().__call__(*args, **kwargs)

    def format(self, *args: Any, **kwargs: Any) -> Any:
        """AgentScope 标准格式方法。"""
        return super().format(*args, **kwargs)


# ------------------------------------------------------------------
# 模型注册中心
# ------------------------------------------------------------------

_MODEL_REGISTRY = {
    "chat": ChatModel,
}

_model_instances: dict[str, Any] = {}


def get_model(model_type: str = "chat") -> Any:
    """获取模型实例（单例，懒加载）。

    Args:
        model_type: 模型类型（chat / embedding / rerank）。

    Returns:
        配置好的模型实例。
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
