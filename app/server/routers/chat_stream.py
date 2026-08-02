# -*- coding: utf-8 -*-
"""SSE 流式 chat 端点。

为什么独立于 api.py 的 chat？
- /api/chat 同步返回，前端要等 5-10 秒才显示结果
- /api/chat/stream 用 SSE 实时推送，前端能"看着 Agent 思考"
- 两个端点共享 chat 主逻辑，通过事件总线解耦

事件流（前端 EventSource 订阅）：
    intent → thinking → text(×N) → tool_call → tool_result → options → done
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.events import ChatEventBus
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["流式对话"])


@router.post("/stream", summary="SSE 流式对话")
async def stream_chat(
    request: Request,
    current=Depends(get_current_user),
) -> StreamingResponse:
    """SSE 流式对话：实时推送 Agent 思考/工具调用/选项过程。

    Body: { "message": str, "session_id": str | None }
    Auth: Bearer token (从 get_current_user 注入 current)
    """
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return StreamingResponse(
            iter(["event: error\ndata: {\"message\":\"消息不能为空\"}\n\n"]),
            media_type="text/event-stream",
        )

    bus = ChatEventBus()

    async def event_generator() -> AsyncGenerator[str, None]:
        # 心跳保活（防止代理超时）
        last_event_time = asyncio.get_event_loop().time()

        async def keepalive():
            nonlocal last_event_time
            while True:
                await asyncio.sleep(15)
                if asyncio.get_event_loop().time() - last_event_time > 15:
                    yield ": keepalive\n\n"

        # 启动后台任务跑主流程
        main_task = asyncio.create_task(_run_chat_pipeline(message, current, bus))

        try:
            async for sse in bus.stream():
                last_event_time = asyncio.get_event_loop().time()
                yield sse
        finally:
            if not main_task.done():
                main_task.cancel()
            bus.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
            "Connection": "keep-alive",
        },
    )


async def _run_chat_pipeline(message: str, current, bus: ChatEventBus) -> None:
    """执行 chat 主流程，往 bus 推事件。

    这里只演示一个简化版（直接用 LLM 回答 + 推事件）。
    完整版应该和 /api/chat 一样：意图识别 + booking / knowledge / casual 分流。
    """
    try:
        # 1. 推送意图识别事件
        from app.server.api import _detect_intent_with_llm
        intent = await _detect_intent_with_llm(message)
        bus.push("intent", {"intent": intent, "mode": intent})

        # 2. 业务调度
        if intent == "booking":
            from app.server.api import _handle_booking_flow
            result = await _handle_booking_flow(message, current.id, "default")
            if isinstance(result, tuple):
                answer, options = result
            else:
                answer, options = result, None
            # 模拟分块输出（实际可以流式）
            for i in range(0, len(answer), 30):
                bus.push("text", {"delta": answer[i:i + 30]})
                await asyncio.sleep(0.02)  # 让人眼能追上
            if options:
                bus.push("options", {"items": options})
            bus.push("done", {"answer": answer, "mode": "booking", "options": options or []})
            return

        # 3. 知识问答 / 闲聊
        from app.core.model_factory import get_model
        from agentscope.message import TextBlock, UserMsg
        model = get_model("chat")
        system = "你是美发行业专业顾问，简洁、专业地回答用户问题。"
        sys_msg = UserMsg(name="system", content=[TextBlock(text=system)])
        user_msg = UserMsg(name="user", content=[TextBlock(text=message)])

        # 流式调用 LLM
        resp = await model([sys_msg, user_msg], stream=True)
        full_text = ""
        if hasattr(resp, "__aiter__"):
            async for chunk in resp:
                if hasattr(chunk, "content") and chunk.content:
                    for block in chunk.content:
                        if hasattr(block, "text") and block.text:
                            bus.push("text", {"delta": block.text})
                            full_text += block.text
        else:
            # 非流式：一次性推
            if hasattr(resp, "content") and resp.content:
                for block in resp.content:
                    if hasattr(block, "text") and block.text:
                        full_text += block.text
                if full_text:
                    bus.push("text", {"delta": full_text})

        bus.push("done", {"answer": full_text, "mode": intent, "options": []})
    except Exception as e:
        logger.exception("SSE chat pipeline failed")
        bus.push("error", {"message": str(e)})
    finally:
        bus.close()
