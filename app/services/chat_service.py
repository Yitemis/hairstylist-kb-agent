# -*- coding: utf-8 -*-
"""Chat 业务服务（P0-1 拆 api.py helper 函数）。

把 5 个 helper 函数从 api.py 抽出来：
- _chat_handler (130 行 chat 主流程)
- _save_ai_message (DB 持久化)
- _save_session_state (state_store + session 状态)
- _is_booking_intent (LLM intent 分类)
- _is_continue_edit_intent (LLM intent 分类)
- _is_view_order_intent (LLM intent 分类)
"""
from __future__ import annotations

import logging
import time as _t
from typing import Optional

from app.utils.llm_extract import extract_text
from app.core.agent_state_store import get_state_store
from app.core.metrics import chat_requests_total, chat_request_duration_seconds

logger = logging.getLogger(__name__)


async def chat_handler(body: dict, ctx) -> dict:
    """Chat 业务主流程（130 行，api.py:406-540 拆出）。"""
    from app.core.model_factory import get_model
    from app.core.knowledge_agent_factory import get_knowledge_agent
    from app.rag.v2_engine import retrieve as rag_retrieve
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage, ChatSession
    from agentscope.message import TextBlock, UserMsg, SystemMsg
    from sqlalchemy import select

    message = (body.get("message") or "").strip()
    user_id = ctx.user_id
    session_id = ctx.session_id

    # 1. 加载历史 20 条
    history_text = ""
    async with async_session_maker() as session:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(20)
        )
        rows = (await session.scalars(stmt)).all()
        for m in reversed(rows):
            role = "用户" if m.role == "user" else "助手"
            history_text += f"{role}：{m.content}\n"

    # 2. 保存 user message
    async with async_session_maker() as session:
        msg = ChatMessage(user_id=user_id, role="user", content=message, session_id=session_id)
        session.add(msg)
        await session.commit()

    # 3. 走 Knowledge Agent
    try:
        agent = await get_knowledge_agent()
        sys_text = "你是美发行业专业顾问。基于知识库检索结果回答，不要编造。"
        if history_text:
            sys_text = sys_text + "\n\n【历史对话】\n" + history_text
        sys_msg = SystemMsg(name="system", role="system", content=[TextBlock(text=sys_text)])
        user_msg = UserMsg(name="user", role="user", content=[TextBlock(text=message)])

        resp = await agent.reply([sys_msg, user_msg])
        text = extract_text(resp)

        # 真实 sources 一次 retrieve
        sources = []
        try:
            rag = await rag_retrieve(query=message, tenant_id=str(user_id), top_k=3)
            if rag.hits:
                sources = [
                    {"document_id": h.document_id, "score": round(h.score, 4),
                     "content": (h.content or "")[:300]}
                    for h in rag.hits
                ]
                if not text:
                    text = "\n".join([f"【{i+1}】{h.content}" for i, h in enumerate(rag.hits[:3])])
        except Exception as e:
            logger.warning("RAG retrieve 失败: %s", e)

        if not text:
            text = "（Agent 返回空）"
        await save_ai_message(user_id, text, mode="knowledge")
        await save_session_state(user_id, session_id, "knowledge", "knowledge", None, None)
        return {
            "answer": text,
            "safety_triggered": False,
            "domain_check": "passed",
            "sources": sources,
            "mode": "knowledge",
        }
    except Exception as e:
        logger.warning("Knowledge Agent 失败, fallback: %s", e)
        err_text = f"抱歉，AI 暂时无法回答：{type(e).__name__}: {e}"
        await save_ai_message(user_id, err_text, mode="error")
        return {
            "answer": err_text,
            "safety_triggered": False,
            "domain_check": "passed",
            "sources": [],
            "mode": "error",
        }


async def save_ai_message(user_id: int, content: str, mode: str = "knowledge") -> None:
    """保存 AI 消息到 chat_messages 表。"""
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    async with async_session_maker() as session:
        msg = ChatMessage(user_id=user_id, role="assistant", content=content, mode=mode)
        session.add(msg)
        await session.commit()


async def save_session_state(
    user_id: int,
    session_id: str,
    intent: str,
    mode: str,
    options: list[dict] | None = None,
    pending_order_id: int | None = None,
) -> None:
    """保存会话状态 (P0-5 修复: 统一存 state_store，删 DB 双写)。"""
    from datetime import datetime
    state = {
        "intent": intent,
        "mode": mode,
        "options": options or [],
        "pending_order_id": pending_order_id,
        "last_call_at": datetime.now().isoformat(),
    }
    store = get_state_store()
    store.save(str(user_id), session_id, "agent_state", state)
    logger.debug("保存 session state (state_store only): %s/%s", user_id, session_id)


async def is_booking_intent(message: str) -> bool:
    """P0-3: LLM 判断是否预约意图。"""
    intent = await _detect_intent_llm(message)
    return intent == "booking"


async def is_continue_edit_intent(message: str) -> bool:
    """P0-3: LLM 判断"继续编辑"意图。"""
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    try:
        model = get_model("chat")
        prompt = f"""判断用户是否在请求"继续编辑/接着填"未完成订单。只回答 yes 或 no。

用户: {message}
答案:"""
        resp = await model(
            [UserMsg(content=prompt, role="user")],
            system_prompt="你是意图分类器。",
        )
        text = extract_text(resp)
        return "yes" in text.strip().lower()
    except Exception:
        return False


async def is_view_order_intent(message: str) -> bool:
    """P0-3: LLM 判断"查看订单"意图。"""
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    try:
        model = get_model("chat")
        prompt = f"""判断用户是否在请求"查看/展示"自己当前订单。只回答 yes 或 no。

用户: {message}
答案:"""
        resp = await model(
            [UserMsg(content=prompt, role="user")],
            system_prompt="你是意图分类器。",
        )
        text = extract_text(resp)
        return "yes" in text.strip().lower()
    except Exception:
        return False


async def _detect_intent_llm(message: str) -> str:
    """内部: LLM 意图分类主入口。"""
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    system = """你是意图分类器。根据用户消息判断意图，只返回 booking / knowledge / casual 之一。"""
    try:
        model = get_model("chat")
        resp = await model(
            [UserMsg(content=message, role="user")],
            system_prompt=system,
        )
        text = extract_text(resp).strip().lower()
        if "booking" in text:
            return "booking"
        if "knowledge" in text:
            return "knowledge"
        return "casual"
    except Exception as e:
        logger.warning("LLM 意图识别失败, fallback: %s", e)
        # 降级: 用 extract_with_llm 看是否提到预约相关信息
        from app.services.intent_extractor import extract_with_llm
        extracted = await extract_with_llm(message)
        if extracted.customer_phone or extracted.appointment_date:
            return "booking"
        return "casual"
