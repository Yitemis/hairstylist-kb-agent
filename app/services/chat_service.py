# -*- coding: utf-8 -*-
"""Chat service (Harness v2: Plugin Pipeline).

P1-3 重构: 从 130 行 if-else -> 50 行 Plugin 调度.
L3 执行编排层 (Harness v2 §3): 10 个 Plugin 串成流水线.
L5 评估与观测 (Harness v2 §6): decision_log 自动落库 + Prometheus 指标.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("__name__")


async def chat_handler(body, ctx, enable_self_rag: bool = False):
    """知识问答主入口 (Harness v2 Plugin Pipeline 调度)."""
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    from app.rag.chat_pipeline import PipelineContext, get_default_runner

    message = (body.get("message") or "").strip()
    user_id = ctx.user_id
    session_id = ctx.session_id

    # 1. 加载历史 (最近 20 条)
    history_text = await _load_history(user_id, session_id)

    # 2. 持久化用户消息
    async with async_session_maker() as session:
        session.add(ChatMessage(
            user_id=user_id, role="user", content=message,
            session_id=session_id,
        ))
        await session.commit()

    # 3. 构造 PipelineContext (10 个字段会被 Plugin 填)
    # 优先用 ctx.tenant_id (B 端多店场景), 缺省 str(user_id) (C 端单租户)
    import os
    default_tenant = os.environ.get("DEFAULT_TENANT_ID") or str(user_id)
    pipeline_ctx = PipelineContext(
        user_id=user_id,
        session_id=session_id,
        message=message,
        history=history_text,
        role=getattr(ctx, "role", "user"),
        tenant_id=getattr(ctx, "tenant_id", default_tenant),
        enable_self_rag=enable_self_rag,
    )

    # 4. 跑 Plugin Pipeline (10 个 Plugin 按 priority 串联)
    runner = get_default_runner()
    pipeline_ctx = await runner.run(pipeline_ctx)

    # 5. 持久化 AI 回复 + LTM 提取
    await save_ai_message(user_id, pipeline_ctx.answer)
    if pipeline_ctx.intent == "knowledge":
        try:
            from app.rag.middleware.long_term_memory import (
                extract_and_save_after_chat,
            )
            saved = await extract_and_save_after_chat(
                user_id, message, pipeline_ctx.answer,
            )
            if saved > 0:
                logger.info("LTM extraction: saved %d new facts", saved)
        except Exception as e:
            logger.debug("LTM extraction failed: %s", e)
    await save_session_state(user_id, session_id, pipeline_ctx.intent, "knowledge")

    return pipeline_ctx.to_response()


async def _load_history(user_id: int, session_id: str, limit: int = 20) -> str:
    """加载最近 N 条历史 (user/assistant 拼成文本)."""
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    from sqlalchemy import select
    async with async_session_maker() as session:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        rows = (await session.scalars(stmt)).all()
    history = ""
    for m in reversed(rows):
        prefix = "user: " if m.role == "user" else "assistant: "
        history += prefix + m.content + "\n"
    return history


async def save_ai_message(user_id: int, content: str, mode: str = "knowledge") -> None:
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    async with async_session_maker() as session:
        session.add(ChatMessage(
            user_id=user_id, role="assistant",
            content=content, mode=mode,
        ))
        await session.commit()


async def save_session_state(
    user_id, session_id, intent, mode,
    options=None, pending_order_id=None,
) -> None:
    from datetime import datetime
    from app.core.agent_state_store import get_state_store
    state = {
        "intent": intent, "mode": mode,
        "options": options or [],
        "pending_order_id": pending_order_id,
        "last_call_at": datetime.now().isoformat(),
    }
    store = get_state_store()
    store.save(str(user_id), session_id, "agent_state", state)


# ===================================================================
# 兼容旧 API: is_booking_intent / is_continue_edit_intent / etc.
# ===================================================================

async def is_booking_intent(message: str) -> bool:
    """判断是否预约意图 (兼容旧 API)."""
    from app.services.chat_dispatcher import classify_intent_llm
    return await classify_intent_llm(message, "") == "booking"


async def is_continue_edit_intent(message: str) -> bool:
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    from app.utils.llm_extract import extract_text
    try:
        model = get_model("chat")
        resp = await model(
            [UserMsg(content="yes or no: " + message, role="user")],
            system_prompt="Intent classifier.",
        )
        return "yes" in extract_text(resp).strip().lower()
    except Exception:
        return False


async def is_view_order_intent(message: str) -> bool:
    return await is_continue_edit_intent(message)
