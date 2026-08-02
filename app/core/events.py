# -*- coding: utf-8 -*-
"""SSE 事件总线：Chat 端点流式响应事件。

为什么需要？
- 用户在 C 端对话时，Agent 内部可能跑 5-10 秒（含多次工具调用）
- 前端要看到"模型正在打字""正在调用工具"的实时反馈
- 不用 SSE：要么等所有完成才显示（5秒白屏），要么前端轮询（浪费资源）
- 用 SSE：服务器推流，前端实时渲染

事件类型（参考 AgentScope 2.0 的 28 种事件）：

| event | data | 含义 |
|-------|------|------|
| intent | {intent, mode} | 意图识别结果 |
| thinking | {text} | 模型思考过程（如有） |
| text | {delta} | 模型输出文本片段（增量） |
| tool_call | {name, args} | 正在调用工具 |
| tool_result | {name, summary} | 工具返回结果摘要 |
| options | {items: [...]} | 列出可点击选项 |
| done | {answer, mode, options} | 完整结果（最终一次） |
| error | {message} | 出错 |
"""
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
