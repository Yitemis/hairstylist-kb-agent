# -*- coding: utf-8 -*-
"""Event types and EventBus for chat pipeline.

借鉴 WeKnora internal/event/event.go.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Pipeline 事件类型."""
    QUERY_REWRITE = "query_rewrite"
    SEARCH = "search"
    RERANK = "rerank"
    FINAL_ANSWER = "final_answer"


@dataclass
class ChatEvent:
    """单次 chat 事件."""
    type: EventType
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0


class EventBus:
    """简单事件总线 (in-process)."""

    def __init__(self):
        self._handlers: dict[EventType, List[Callable]] = {}

    def on(self, event_type: EventType, handler: Callable) -> None:
        """注册 handler."""
        self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: ChatEvent) -> None:
        """触发事件 (同步, 顺序执行)."""
        for h in self._handlers.get(event.type, []):
            try:
                h(event)
            except Exception as e:
                logger.error("Handler %s failed: %s", h.__name__, e)

    def clear(self) -> None:
        self._handlers.clear()


__all__ = ["ChatEvent", "EventBus", "EventType"]
