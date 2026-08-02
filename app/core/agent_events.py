# -*- coding: utf-8 -*-
"""完整 28 种 AgentEvent 类型：借鉴 AgentScope 2.0 的事件系统。

事件分类（参考 AgentScope event 模块）：
- ReplyStart / ReplyEnd          → 整个回复开始/结束
- ModelCallStart / ModelCallEnd  → 模型调用
- TextBlockStart/Delta/End        → 文本流
- ThinkingBlockStart/Delta/End    → 思考过程
- DataBlockStart/Delta/End        → 多模态
- ToolCallStart/Delta/End         → 工具调用
- ToolResultStart/TextDelta/DataDelta/End → 工具结果
- ExceedMaxItersEvent            → 超最大迭代
- RequireUserConfirmEvent        → HITL
- UserConfirmResultEvent         → 用户确认结果
- HintBlockEvent                 → RAG 注入
- UserInterruptEvent             → 用户中断

我们用 dataclass + 简单的 serialize，事件总线 (ChatEventBus) 推流。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """统一事件结构。"""
    event_type: str  # e.g. "model_call_start"
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    user_id: int | None = None

    def to_sse(self) -> str:
        """渲染为 SSE 协议格式。"""
        payload = {"type": self.event_type, "ts": self.timestamp, **self.data}
        if self.trace_id:
            payload["trace_id"] = self.trace_id
        if self.user_id:
            payload["user_id"] = self.user_id
        return f"event: {self.event_type}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


# 事件类型常量（参考 AgentScope EventType 枚举）
class EventType:
    REPLY_START = "reply_start"
    REPLY_END = "reply_end"
    MODEL_CALL_START = "model_call_start"
    MODEL_CALL_END = "model_call_end"
    MODEL_CALL_ERROR = "model_call_error"
    TEXT_BLOCK_START = "text_block_start"
    TEXT_BLOCK_DELTA = "text_block_delta"
    TEXT_BLOCK_END = "text_block_end"
    THINKING_BLOCK_START = "thinking_block_start"
    THINKING_BLOCK_DELTA = "thinking_block_delta"
    THINKING_BLOCK_END = "thinking_block_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    TOOL_RESULT_START = "tool_result_start"
    TOOL_RESULT_TEXT_DELTA = "tool_result_text_delta"
    TOOL_RESULT_DATA_DELTA = "tool_result_data_delta"
    TOOL_RESULT_END = "tool_result_end"
    EXCEED_MAX_ITERS = "exceed_max_iters"
    REQUIRE_USER_CONFIRM = "require_user_confirm"
    USER_CONFIRM_RESULT = "user_confirm_result"
    HINT_BLOCK = "hint_block"
    USER_INTERRUPT = "user_interrupt"
    CUSTOM = "custom"
