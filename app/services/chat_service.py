# -*- coding: utf-8 -*-
"""Chat service (P0-3: self_rag + remove pipeline)."""
from __future__ import annotations
import logging
from app.utils.llm_extract import extract_text
logger = logging.getLogger("__name__")

async def chat_handler(body, ctx, enable_self_rag=False):
    from app.rag.v2_engine import retrieve
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    from app.rag.agentic.self_rag import self_rag_retrieve
    from sqlalchemy import select
    message = (body.get("message") or "").strip()
    user_id = ctx.user_id
    session_id = ctx.session_id
    history_text = ""
    async with async_session_maker() as session:
        stmt = select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id).order_by(ChatMessage.id.desc()).limit(20)
        rows = (await session.scalars(stmt)).all()
        for m in reversed(rows):
            history_text += ("user: " if m.role == "user" else "assistant: ") + m.content + chr(10)
    async with async_session_maker() as session:
        session.add(ChatMessage(user_id=user_id, role="user", content=message, session_id=session_id))
        await session.commit()
    try:
        if enable_self_rag:
            async def _retrieve_fn(q, t, k):
                return await retrieve(query=q, tenant_id=t, top_k=k, enable_rerank=False)
            out = await self_rag_retrieve(query=message, retrieve_fn=_retrieve_fn, tenant_id=str(user_id), top_k=3, max_retries=2, confidence_threshold=0.4)
            hits = out["hits"]
            evaluation = out["evaluation"]
            attempts = out["attempts"]
        else:
            result = await retrieve(query=message, tenant_id=str(user_id), top_k=3, enable_rerank=False)
            hits = list(result.hits)
            evaluation = None
            attempts = 1
        reranked_hits = await _rerank_with_enrich(query=message, hits=hits)
        context_parts = []
        for i, h in enumerate(reranked_hits[:5], 1):
            c2 = (h.content or "")[:500]
            if c2:
                context_parts.append("[" + str(i) + "] " + c2)
        nl = chr(10) + chr(10)
        context_text = nl.join(context_parts) if context_parts else "(no results)"

        # ========== L4: 加载用户长期记忆注入 system prompt ==========
        from app.rag.middleware.long_term_memory import load_user_facts
        user_facts = await load_user_facts(user_id)
        logger.info("LTM injection: loaded %d facts for user=%d", len(user_facts), user_id)

        answer = await _generate_answer(
            query=message, context=context_text, history=history_text,
            user_facts=user_facts,
        )
        sources = []
        for h in reranked_hits[:5]:
            sources.append({"document_id": h.document_id, "score": round(getattr(h, "rerank_score", h.score), 4), "content": (h.content or "")[:300]})
        self_rag_meta = {"enabled": enable_self_rag, "attempts": attempts}
        if evaluation:
            self_rag_meta["confidence"] = evaluation.confidence
            self_rag_meta["needs_retry"] = evaluation.needs_retry
        await save_ai_message(user_id, answer)

        # ========== L4: end-of-turn 自动提取事实 ==========
        from app.rag.middleware.long_term_memory import extract_and_save_after_chat
        saved = await extract_and_save_after_chat(user_id, message, answer)
        if saved > 0:
            logger.info("LTM extraction: saved %d new facts for user=%d", saved, user_id)

        await save_session_state(user_id, session_id, "knowledge", "knowledge")
        return {"answer": answer, "sources": sources, "mode": "knowledge", "self_rag": self_rag_meta}
    except Exception as e:
        logger.warning("chat_handler failed: %s", e)
        err_text = "Sorry: " + type(e).__name__ + ": " + str(e)
        await save_ai_message(user_id, err_text, mode="error")
        return {"answer": err_text, "sources": [], "mode": "error", "self_rag": {"enabled": enable_self_rag, "error": str(e)}}

async def _rerank_with_enrich(query, hits):
    if not hits or len(hits) < 2:
        return hits
    try:
        from app.embedding import build_rerank_model
        from app.rag.chat_pipeline.enrich import get_enriched_passage, sanitize_passage_for_rerank
        from app.rag.retriever.normalizer import normalize_score
        from app.db.models import ParentChunk
        from app.db.session import async_session_maker
        from sqlalchemy import select
        parent_ids = [h.parent_id for h in hits if h.parent_id]
        parent_texts = {}
        if parent_ids:
            async with async_session_maker() as session:
                stmt = select(ParentChunk).where(ParentChunk.parent_id.in_(parent_ids))
                rows = (await session.execute(stmt)).scalars().all()
                for r in rows:
                    parent_texts[r.parent_id] = r.content
        passages = []
        for h in hits:
            c2 = parent_texts.get(h.parent_id, h.content or "")
            passage = get_enriched_passage({"content": c2, "filename": getattr(h, "source", "")}, max_chars=1500)
            passage = sanitize_passage_for_rerank(passage)
            passages.append(passage)
        reranker = build_rerank_model()
        scores = await reranker([[query, p] for p in passages])
        for h, score in zip(hits, scores.scores):
            h.rerank_score = normalize_score(float(score), engine_type="rerank")
        hits.sort(key=lambda h: h.rerank_score, reverse=True)
    except Exception as e:
        logger.warning("Rerank failed: %s", e)
    return hits

async def _generate_answer(query, context, history, user_facts=None, model_name="default"):
    from app.core.knowledge_agent_factory import get_knowledge_agent
    from agentscope.message import TextBlock, UserMsg
    nl = chr(10) + chr(10)

    # ========== L4: 注入用户长期记忆 ==========
    facts_injection = ""
    if user_facts:
        from app.core.long_term_memory import build_facts_injection
        facts_injection = build_facts_injection(user_facts[:20])
        if facts_injection:
            facts_injection = facts_injection + nl

    # ========== L2: 注入相关 Skills ==========
    skill_injection = ""
    try:
        from app.core.skill import build_skill_injection
        skill_injection = build_skill_injection(query)
        if skill_injection:
            skill_injection = skill_injection + nl
    except Exception as e:
        logger.debug("Skill injection failed: %s", e)

    # ========== L6: 监控上下文利用率 ==========
    from app.rag.context_monitor import (
        check_and_warn, should_compress
    )

    # 把所有上下文拼到 user message（新 AgentScope 限制 input 只能 user/assistant）
    context_block = (
        facts_injection +
        skill_injection +
        "[KB]" + chr(10) + context
    )
    if history:
        context_block += nl + "[History]" + chr(10) + history

    full_prompt = context_block + nl + query
    usage = check_and_warn(full_prompt, model_name=model_name)
    logger.info(
        "Context usage: %d tokens (%.1f%%) zone=%s",
        usage.used_tokens, usage.utilization * 100, usage.zone.value,
    )

    # 超阈值自动压缩
    if should_compress(usage) and history:
        logger.warning("Context zone=%s, auto-truncating history", usage.zone.value)
        history_lines = history.strip().split(chr(10))
        if len(history_lines) > 10:
            history = chr(10).join(history_lines[-10:]) + nl + "[...历史已压缩...]"
        # 重新拼
        full_prompt = (
            facts_injection + skill_injection +
            "[KB]" + chr(10) + context + nl +
            "[History]" + chr(10) + history + nl + query
        )

    agent = await get_knowledge_agent()
    user_msg = UserMsg(name="user", content=[TextBlock(text=full_prompt)])
    resp = await agent.reply([user_msg])
    text = extract_text(resp)
    return text or "(empty)"

async def save_ai_message(user_id, content, mode="knowledge"):
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    async with async_session_maker() as session:
        session.add(ChatMessage(user_id=user_id, role="assistant", content=content, mode=mode))
        await session.commit()

async def save_session_state(user_id, session_id, intent, mode, options=None, pending_order_id=None):
    from datetime import datetime
    from app.core.agent_state_store import get_state_store
    state = {"intent": intent, "mode": mode, "options": options or [], "pending_order_id": pending_order_id, "last_call_at": datetime.now().isoformat()}
    store = get_state_store()
    store.save(str(user_id), session_id, "agent_state", state)

async def is_booking_intent(message):
    intent = await _detect_intent_llm(message)
    return intent == "booking"

async def is_continue_edit_intent(message):
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    try:
        model = get_model("chat")
        resp = await model([UserMsg(content="yes or no: " + message, role="user")], system_prompt="Intent classifier.")
        return "yes" in extract_text(resp).strip().lower()
    except Exception:
        return False

async def is_view_order_intent(message):
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    try:
        model = get_model("chat")
        resp = await model([UserMsg(content="yes or no: " + message, role="user")], system_prompt="Intent classifier.")
        return "yes" in extract_text(resp).strip().lower()
    except Exception:
        return False

async def _detect_intent_llm(message):
    from app.core.model_factory import get_model
    from agentscope.message import UserMsg
    system = "Return booking/knowledge/casual only."
    try:
        model = get_model("chat")
        resp = await model([UserMsg(content=message, role="user")], system_prompt=system)
        text = extract_text(resp).strip().lower()
        if "booking" in text:
            return "booking"
        if "knowledge" in text:
            return "knowledge"
        return "casual"
    except Exception:
        return "casual"
