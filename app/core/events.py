# -*- coding: utf-8 -*-
"""事件总线。"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatEvent:
    """单个 SSE 事件。"""
    event: str  # 事件名（对应 SSE event 字段）
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """序列化成 SSE 协议格式。

        格式：
            event: <event>
            data: <json>
            <blank line>
        """
        return f"event: {self.event}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


class ChatEventBus:
    """事件总线：Agent 内部往里推，前端通过 SSE 拉取。

    用法：
        bus = ChatEventBus()
        bus.push("text", {"delta": "你好"})
        bus.push("done", {"answer": "..."})
        async for sse in bus.stream():
            yield sse
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    def push(self, event: str, data: dict[str, Any] | None = None) -> None:
        """推一个事件到流。线程/协程安全。"""
        if self._closed:
            return
        self._queue.put_nowait(ChatEvent(event=event, data=data or {}))

    def close(self) -> None:
        """关闭流（前端会收到 EOS）。"""
        self._closed = True
        self._queue.put_nowait(None)  # 哨兵

    async def stream(self):
        """异步生成器：把事件转成 SSE 协议。"""
        try:
            while True:
                evt: ChatEvent | None = await self._queue.get()
                if evt is None:
                    break
                yield evt.to_sse()
        finally:
            self._closed = True
