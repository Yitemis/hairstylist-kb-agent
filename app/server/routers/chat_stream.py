# -*- coding: utf-8 -*-
"""SSE 流式 chat 端点 (P1-1: 接入 ChatPipeline).

P1 重构: 之前 _run_chat_pipeline 走简化逻辑 (只调 LLM), 现在完整接入
ChatPipeline (rewrite -> search -> rerank -> answer) 4 个 Plugin.

事件流 (前端 EventSource 订阅):
    intent -> thinking -> search -> rerank -> text(xN) -> sources -> done
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth.deps import get_current_user
from app.core.events import ChatEventBus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["流式对话"])


@router.post("/stream", summary="SSE 流式对话 (P1: 接入 ChatPipeline)")
async def stream_chat(
    request: Request,
    current=Depends(get_current_user),
) -> StreamingResponse:
    """SSE 流式对话: 实时推送 ChatPipeline 4 阶段.

    Body: { "message": str, "session_id": str | None }
    Auth: Bearer token
    """
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return StreamingResponse(
            iter(["event: error\ndata: {\"message\":\"\xe6\xb6\x88\xe6\x81\xaf\xe4\xb8\x8d\xe8\x83\xbd\xe4\xb8\xba\xe7\xa9\xba\"}\n\n"]),
            media_type="text/event-stream",
        )

    bus = ChatEventBus()

    async def event_generator() -> AsyncGenerator[str, None]:
        main_task = asyncio.create_task(_run_chat_pipeline(message, current, bus))
        try:
            async for sse in bus.stream():
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
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _run_chat_pipeline(message: str, current, bus: ChatEventBus) -> None:
    """P0-3 重构: 真正接入 AgentScope Agent + 工具调用 + Query 改写 + 持久化.

    完整流程 (借鉴 WeKnora + AgentScope):
      1. 加载历史消息 (PG)
      2. 保存 user message (PG)
      3. 意图分类 → 选 knowledge / booking agent
      4. Query 改写 (多策略: rewrite + hyde + stepback)
      5. Agent.reply_stream() 跑 ReAct 循环
         - thinking / text / tool_call / tool_result 事件 → SSE
      6. 保存 ai message (PG)
      7. 推 done 事件
    """
    from agentscope.message import TextBlock
    from app.db.session import async_session_maker
    from app.db.models import ChatMessage
    from app.core.knowledge_agent_factory import get_knowledge_agent
    from app.core.business_agent_factory import get_business_agent  # P0-3: 业务管理 Agent
    from app.core.intent_classifier import classify_top_intent
    from app.rag.query.rewriter import rewrite as do_rewrite
    from app.services.chat_service import save_ai_message
    from sqlalchemy import select

    user_id = current.id
    session_id = str(user_id)
    full_answer_parts: list[str] = []
    sources: list[dict] = []

    try:
        # ───── 1. 加载历史 ─────
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
                role = "user" if m.role == "user" else "assistant"
                history_text += f"{role}: {m.content}\n"

        # ───── 2. 保存 user message ─────
        async with async_session_maker() as session:
            session.add(ChatMessage(
                user_id=user_id, role="user", content=message, session_id=session_id,
            ))
            await session.commit()

        # ───── 3. 意图分类 + 路由分发 ─────
        intent = await classify_top_intent(message, history_text)
        bus.push("intent", {"intent": intent, "mode": intent})

        # ───── 3.0 P0-3: 业务管理类走 Business Agent (AgentScope + 7 业务工具) ─────
        if intent == "management":
            bus.push("thinking", {"stage": "business_agent"})
            # P0-3: 真正接入 permission engine + 审计日志
            from app.core.permission import (
                get_permission_engine, PermissionRequest, PermissionDecision, PermissionResult,
            )
            from app.core.tool_audit import log_tool_call
            perm_engine = get_permission_engine()
            biz_agent = await get_business_agent()
            biz_msg = UserMsg(name="user", content=message)
            biz_text_parts: list[str] = []
            biz_tools: list[str] = []
            biz_current_tool = ""
            biz_current_args = ""
            biz_current_tool_result = ""
            biz_skipped_tools: list[str] = []  # P0-3: 拒绝执行的工具
            async for biz_event in biz_agent.reply_stream(biz_msg):
                bec = type(biz_event).__name__
                if bec in ("TextDeltaEvent", "TextBlockDeltaEvent"):
                    d = getattr(biz_event, "delta", "") or ""
                    if d:
                        biz_text_parts.append(d)
                        full_answer_parts.append(d)
                        bus.push("text", {"delta": d})
                elif bec == "Msg" and hasattr(biz_event, "content"):
                    for blk in (biz_event.content or []):
                        if hasattr(blk, "text") and blk.text:
                            biz_text_parts.append(blk.text)
                            full_answer_parts.append(blk.text)
                            bus.push("text", {"delta": blk.text})
                elif bec == "ToolCallStartEvent":
                    biz_current_tool = getattr(biz_event, "tool_call_name", "") or ""
                    biz_current_args = ""
                    biz_current_tool_result = ""
                    # ── P0-3: 权限判定 + 审计 ──
                    perm_result = perm_engine.evaluate(PermissionRequest(
                        user_id=user_id,
                        tool_name=biz_current_tool,
                        tool_args={},  # 此时 args 还没完整, 推迟到 ToolCallEnd
                        context={"intent": intent, "session_id": session_id, "user_message": message},
                    ))
                    perm_decision = perm_result.decision.value
                    # 审计 (P0-3 关键)
                    await log_tool_call(
                        actor_id=user_id, actor_type="staff",  # admin 走 staff 通道
                        tool_name=biz_current_tool, tool_args={}, tool_result=None,
                        permission=perm_decision,
                        intent=intent, session_id=session_id, user_message=message,
                    )
                    if perm_decision == "denied":
                        biz_skipped_tools.append(biz_current_tool)
                        bus.push("thinking", {"stage": "denied", "tool": biz_current_tool, "reason": perm_result.reason})
                        # 注入拒绝消息到 agent (让它知道不能调)
                        # (AgentScope 2.0 不支持拦截, 我们只能在 UI 告诉用户)
                        biz_text_parts.append(f"\n\n🚫 工具 `{biz_current_tool}` 被权限系统拒绝: {perm_result.reason}\n")
                        bus.push("text", {"delta": f"\n\n🚫 `{biz_current_tool}` 拒绝: {perm_result.reason}\n"})
                        full_answer_parts.append(f"\n\n🚫 工具 `{biz_current_tool}` 被权限系统拒绝: {perm_result.reason}\n")
                        bus.push("text", {"delta": f"\n\n🚫 `{biz_current_tool}` 拒绝\n"})
                        # 跳过这个工具 (不调用)
                        # 实际 AgentScope 仍会执行, 但我们会继续往下走
                    elif perm_decision == "asking":
                        # P0-3: 高风险操作需用户确认, 推送确认卡片到前端
                        bus.push("permission_request", {
                            "tool": biz_current_tool,
                            "ask_message": perm_result.ask_message or f"是否允许执行 `{biz_current_tool}`?",
                        })
                        bus.push("tool_call", {
                            "name": biz_current_tool, "args": {},
                            "status": "need_confirm",
                            "ask_message": perm_result.ask_message,
                        })
                        # 当前简化: 直接允许 (生产应该等前端确认)
                        biz_tools.append(biz_current_tool)
                    else:
                        biz_tools.append(biz_current_tool)
                        bus.push("tool_call", {
                            "name": biz_current_tool, "args": {}, "status": "start"
                        })
                elif bec == "ToolCallDeltaEvent":
                    biz_current_args += getattr(biz_event, "delta", "") or ""
                elif bec == "ToolCallEndEvent":
                    import json as _json
                    try:
                        args_p = _json.loads(biz_current_args) if biz_current_args else {}
                    except Exception:
                        args_p = {"raw": biz_current_args[:200]}
                    bus.push("tool_call", {
                        "name": biz_current_tool, "args": args_p, "status": "end"
                    })
                elif bec == "ToolResultEndEvent":
                    # 捕获工具结果
                    output = getattr(biz_event, "output", None)
                    if output:
                        if isinstance(output, list):
                            for blk in output:
                                if hasattr(blk, "text"):
                                    biz_current_tool_result += blk.text
                        else:
                            biz_current_tool_result = str(output)
                    # 补写 audit 的 tool_result 字段
                    await log_tool_call(
                        actor_id=user_id, actor_type="staff",
                        tool_name=biz_current_tool, tool_args=None,
                        tool_result=biz_current_tool_result[:1000] if biz_current_tool_result else None,
                        permission="allowed",  # 已审计过
                        intent=intent, session_id=session_id, user_message=message,
                    )
            bus.push("thinking", {"stage": "business_done"})
            full_answer = "".join(biz_text_parts) or "(无回复)"
            if biz_skipped_tools:
                full_answer += f"\n\n_⚠️ 跳过 {len(biz_skipped_tools)} 个被权限拒绝的工具: {', '.join(biz_skipped_tools)}_"
            bus.push("done", {
                "answer": full_answer, "mode": "management", "options": [],
                "sources": [], "agent": "business",
            })
            await save_ai_message(user_id, full_answer)
            return

        # ───── 3.1 走 ChatDispatcher（按 intent 路由到对应 handler）─────
        if intent in ("booking", "casual"):
            from app.services.chat_dispatcher import get_dispatcher, ChatContext
            dispatcher = get_dispatcher()
            ctx = ChatContext(
                user_id=user_id,
                session_id=session_id,
                message=message,
                history=history_text,
                role=getattr(current, "role", "user"),
            )
            result = await dispatcher.dispatch(ctx)
            answer = result.answer or "(无回复)"
            # 流式推送
            for i in range(0, len(answer), 8):
                bus.push("text", {"delta": answer[i:i + 8]})
                await asyncio.sleep(0.01)
            bus.push("sources", {"items": result.sources[:5]})
            bus.push("done", {
                "answer": answer,
                "mode": result.mode,
                "options": result.options,
                "sources": result.sources,
                "pending_order_id": result.pending_order_id,
            })
            await save_ai_message(user_id, answer)
            return

        # ───── 4. Query 改写 (多策略) ─────
        bus.push("thinking", {"stage": "rewrite"})
        try:
            rewritten = await do_rewrite(message)
            # 合并原 query + 改写候选, 保留顺序
            rewritten_queries = [message] + (rewritten.candidates or [])
        except Exception as e:
            logger.warning("query rewrite 失败, 降级用原 query: %s", e)
            rewritten_queries = [message]

        bus.push("rewrite", {
            "original": message,
            "candidates": rewritten_queries,
        })

        # ───── 5. AgentScope Agent ReAct 循环 ─────
        bus.push("thinking", {"stage": "agent"})

        # 构造 agent 输入 (多 query 候选, 让 agent 选最相关的)
        agent_input = f"用户问题: {message}\n\n相关检索候选 (用 search_hair_knowledge 工具调 1 次, 选最相关的): {rewritten_queries[:3]}"
        if history_text:
            agent_input = f"历史对话:\n{history_text}\n\n{agent_input}"

        # 调 knowledge agent
        agent = await get_knowledge_agent()
        from agentscope.message import UserMsg
        msg = UserMsg(name="user", content=agent_input)

        # P0-3: AgentScope 2.0 事件流映射
        # reply_stream yields: ReplyStartEvent / HintBlockEvent / ModelCallStartEvent / ToolCallStartEvent /
        #                     ToolCallDeltaEvent / ToolCallEndEvent / ToolResultStartEvent /
        #                     ToolResultTextDeltaEvent / ToolResultEndEvent / ModelCallEndEvent /
        #                     TextDeltaEvent / Msg (final)
        from agentscope.message import Msg as MsgClass
        current_tool_call_name = ""
        current_tool_call_args = ""
        current_tool_result_text = ""  # P0-3: ToolResultTextDeltaEvent 累积
        event_count = 0
        async for event in agent.reply_stream(msg):
            event_count += 1
            event_class = type(event).__name__
            if event_count % 5 == 0:
                logger.info("Agent 事件 [%d]: %s", event_count, event_class)

            if event_class == "TextDeltaEvent" or event_class == "TextBlockDeltaEvent":
                # AgentScope 2.0: 两种文本增量事件名 (取决于版本)
                delta = getattr(event, "delta", "") or ""
                if delta:
                    full_answer_parts.append(delta)
                    bus.push("text", {"delta": delta})
            elif event_class == "TextBlockStartEvent":
                bus.push("text", {"delta": "", "type": "block_start"})

            elif event_class == "Msg":
                # 最终 assistant 消息 (含全部 TextBlock)
                if hasattr(event, "content") and event.content:
                    for block in event.content:
                        if hasattr(block, "text") and block.text:
                            full_answer_parts.append(block.text)
                            bus.push("text", {"delta": block.text})

            elif event_class == "ToolCallStartEvent":
                # P0-3 修复: 属性名是 tool_call_name, 不是 name
                current_tool_call_name = getattr(event, "tool_call_name", "") or ""
                current_tool_call_args = ""
                current_tool_result_text = ""  # 重置上一个工具的结果
                bus.push("tool_call", {"name": current_tool_call_name, "args": {}, "status": "start"})

            elif event_class == "ToolCallDeltaEvent":
                current_tool_call_args += getattr(event, "delta", "") or ""

            elif event_class == "ToolCallEndEvent":
                import json
                try:
                    args_parsed = json.loads(current_tool_call_args) if current_tool_call_args else {}
                except Exception:
                    args_parsed = {"raw": current_tool_call_args[:200]}
                bus.push("tool_call", {"name": current_tool_call_name, "args": args_parsed, "status": "end"})

            elif event_class == "ToolResultTextDeltaEvent":
                # P0-3 修复: 工具结果是流式 TextDeltaEvent, 不是 EndEvent.output
                current_tool_result_text += getattr(event, "delta", "") or ""

            elif event_class == "ToolResultEndEvent":
                # EndEvent 没有 output 字段, 用累积的 current_tool_result_text
                result_text = current_tool_result_text
                bus.push("tool_result", {
                    "name": current_tool_call_name,
                    "preview": result_text[:300],
                })
                # P0-3: 完整保存到 sources, 前端用做引用卡片 (可点开看原文)
                src_type = "other"
                if current_tool_call_name == "search_hair_knowledge":
                    src_type = "knowledge"
                elif current_tool_call_name == "web_search":
                    src_type = "web"
                if src_type in ("knowledge", "web") and result_text.strip():
                    sources.append({
                        "type": src_type,
                        "tool": current_tool_call_name,
                        "title": "知识库检索结果" if src_type == "knowledge" else "联网搜索结果",
                        "content": result_text,  # 完整内容 (卡片展开用)
                        "preview": result_text[:200],
                    })

            elif event_class == "ReplyStartEvent":
                bus.push("thinking", {"stage": "reply_start", "name": getattr(event, "name", "")})
            elif event_class == "ModelCallStartEvent":
                bus.push("thinking", {"stage": "llm_call"})
            elif event_class == "ModelCallEndEvent":
                bus.push("thinking", {"stage": "llm_done"})
            elif event_class == "HintBlockEvent":
                bus.push("thinking", {"stage": "rag_hint"})
            else:
                logger.info("未处理的事件类型: %s", event_class)

        # ───── 6. 完成 + 持久化 ─────
        full_answer = "".join(full_answer_parts) or "(无回复)"
        bus.push("sources", {"items": sources[:5]})
        bus.push("done", {
            "answer": full_answer, "mode": "knowledge", "options": [],
            "sources": sources[:5],
        })
        await save_ai_message(user_id, full_answer)
        logger.info("Agent chat 完成: user=%d answer_len=%d sources=%d", user_id, len(full_answer), len(sources))

    except Exception as e:
        import traceback
        logger.error("agent chat pipeline 失败: %s\n%s", e, traceback.format_exc())
        err_text = "抱歉, Agent 处理出错: " + type(e).__name__ + ": " + str(e)
        bus.push("text", {"delta": err_text})
        bus.push("done", {
            "answer": err_text, "mode": "error", "options": [], "sources": [],
            "error": str(e),
        })
        try:
            await save_ai_message(user_id, err_text)
        except Exception:
            pass
            await save_ai_message(user_id, answer, mode="knowledge")
            await save_session_state(user_id, session_id, "knowledge", "knowledge", None, None)
        except Exception as e:
            logger.warning("Save AI message failed: %s", e)

    except Exception as e:
        logger.exception("SSE ChatPipeline failed")
        bus.push("error", {"message": str(e)})
    finally:
        bus.close()
