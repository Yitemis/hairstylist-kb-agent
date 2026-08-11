# -*- coding: utf-8 -*-
"""chat 子路由 (从 api.py 拆出, N14 修复)。

包含 6 个端点:
- GET    /api/chat/history            获取用户对话历史
- DELETE /api/chat/history            清空用户对话历史
- GET    /api/chat/sessions           列出用户的所有会话
- GET    /api/chat/sessions/{id}/state  获取会话状态
- POST   /api/chat/sessions           创建/保存会话状态
- DELETE /api/chat/sessions/{id}      删除会话
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user
from app.db.models import ChatMessage, ChatSession
from app.db.session import async_session_maker, get_session
from app.services import chat_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/history", summary="获取用户对话历史")
async def get_chat_history(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> dict:
    """获取当前登录用户最近的对话历史。"""
    user_id = current.id
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()  # 返回正序

    return {
        "messages": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "role": m.role,
                "content": m.content,
                "order_id": m.order_id,
                "mode": m.mode,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.delete("/chat/history", summary="清空用户对话历史")
async def clear_chat_history(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """清空当前用户所有对话历史。"""
    stmt = delete(ChatMessage).where(ChatMessage.user_id == current.id)
    await session.execute(stmt)
    await session.commit()
    return {"status": "ok", "message": "对话已清空"}


@router.get("/chat/sessions", summary="列出用户的所有会话")
async def list_chat_sessions(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """list user sessions (P0-5: unified from state_store, no merge of two sources).

    之前: file_sessions + db_sessions 两个数据源合并
    现在: 统一从 AgentStateStore (Redis) 读, 前端只看到一个 source
    """
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    session_ids = store.list_session_ids(str(current.id))

    # 构造统一的 sessions 列表 (with metadata for each session)
    sessions = []
    for sid in session_ids:
        state = store.get(str(current.id), sid, "agent_state")
        if state:
            sessions.append({
                "session_id": sid,
                "intent": state.get("intent"),
                "mode": state.get("mode"),
                "pending_order_id": state.get("pending_order_id"),
                "last_call_at": state.get("last_call_at"),
                "extra": state.get("extra", {}),
            })
    return {
        "sessions": sessions,
        "total": len(sessions),
    }


@router.get("/chat/sessions/{session_id}/state", summary="获取会话状态")
async def get_session_state(
    session_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """从 AgentStateStore 恢复会话状态。"""
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    state = store.get(str(current.id), session_id, "agent_state")
    if state is None:
        raise HTTPException(status_code=404, detail="会话状态不存在")
    return state


@router.post("/chat/sessions", summary="创建/保存会话状态")
async def save_session(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """从 body 恢复会话状态。"""
    session_id = body.get("session_id") or "default"
    await chat_service.save_session_state(
        user_id=current.id,
        session_id=session_id,
        intent=body.get("intent", "casual"),
        mode=body.get("mode", "casual"),
        options=body.get("options"),
        pending_order_id=body.get("pending_order_id"),
    )
    return {"status": "ok", "session_id": session_id}


@router.delete("/chat/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """删除指定会话 (state_store + messages)。"""
    # 1. 删 state_store
    from app.core.agent_state_store import get_state_store
    store = get_state_store()
    store.delete(str(current.id), session_id)

    # 2. 删 messages + sessions
    async with async_session_maker() as db_session:
        await db_session.execute(delete(ChatMessage).where(ChatMessage.user_id == current.id))
        await db_session.execute(delete(ChatSession).where(
            ChatSession.user_id == current.id,
            ChatSession.session_id == session_id,
        ))
        await db_session.commit()

    return {"status": "ok", "message": f"会话 {session_id} 已删除"}
