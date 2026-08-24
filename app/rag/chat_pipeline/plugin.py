# -*- coding: utf-8 -*-
"""Plugin 基类: Pipeline 编排的基础单元.

每个 Plugin 处理 Pipeline 一类事件, 返回新 ctx (或 in-place 改 ctx).
Plugin 通过 priority 决定执行顺序, 由 PluginRunner 串联.

使用示例:
    class MyPlugin(Plugin):
        name = "my_plugin"
        priority = 50

        async def on_event(self, ctx: PipelineContext) -> PipelineContext:
            ctx.answer = "hello"
            return ctx
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Type

from app.rag.chat_pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class Plugin(ABC):
    """Plugin 基类.

    Attributes:
        name: Plugin 名称 (用于 metric / log / 调试)
        priority: 优先级 (越小越先执行; 同 priority 按注册顺序)
        enabled: 是否启用 (调试 / A/B 可关)
    """

    name: str = "base_plugin"
    priority: int = 100
    enabled: bool = True

    @abstractmethod
    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        """Plugin 入口: 处理 ctx, 返回新 ctx.

        Args:
            ctx: Pipeline 共享上下文

        Returns:
            更新后的 ctx (可 in-place 改, 也可返回新对象)
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Plugin {self.name} priority={self.priority} enabled={self.enabled}>"


__all__ = ["Plugin"]
