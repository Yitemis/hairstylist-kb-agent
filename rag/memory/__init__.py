# -*- coding: utf-8 -*-
"""对话记忆模块：短期窗口 + 长期事实 + 统一管理器。

* :class:`ShortTermMemory` —— 滑动窗口短期记忆（上下文窗口 + 压缩）；
* :class:`InMemoryFactStore` / :class:`Fact` —— 长期记忆（用户事实沉淀）；
* :class:`MemoryManager` —— 编排"短期 → 长期 → 短期"记忆循环。
"""
from __future__ import annotations

from .long_term import Fact, FactStoreBase, InMemoryFactStore, render_facts
from .manager import MemoryManager
from .short_term import ShortTermMemory, Turn

__all__ = [
    "ShortTermMemory",
    "Turn",
    "Fact",
    "FactStoreBase",
    "InMemoryFactStore",
    "render_facts",
    "MemoryManager",
]
