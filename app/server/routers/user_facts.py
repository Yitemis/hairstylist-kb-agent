# -*- coding: utf-8 -*-
"""user_facts 路由 (从 api.py 拆出)。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user
from app.db.session import get_session

router = APIRouter(prefix="/api", tags=["user_facts"])


@router.get("/user/facts", summary="获取当前用户所有长期事实")
async def get_user_facts(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[dict]:
    """获取当前用户所有已知偏好（如：常用发型师、过敏产品、常去分店）。"""
    from app.core.long_term_memory import get_user_facts
    return await get_user_facts(current.id)


@router.delete("/user/facts/{fact_key}", summary="删除一条用户事实")
async def delete_user_fact(
    fact_key: str,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """删除一条用户事实（如用户改主意了要忘记某个偏好）。"""
    from app.db.models import UserProfile
    from app.db.session import async_session_maker
    from sqlalchemy import delete
    async with async_session_maker() as session:
        await session.execute(delete(UserProfile).where(
            UserProfile.user_id == current.id,
            UserProfile.fact_key == fact_key,
        ))
        await session.commit()
    return {"status": "ok", "message": f"已删除 {fact_key}"}


@router.post("/user/facts/extract", summary="从一段对话中提取事实")
async def extract_facts_endpoint(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """手动触发事实提取（一般由 chat 端点自动调用，这里暴露给测试）。"""
    from app.core.long_term_memory import extract_facts_with_llm, save_facts
    user_message = body.get("user_message", "")
    ai_message = body.get("ai_message", "")
    facts = await extract_facts_with_llm(current.id, user_message, ai_message)
    saved = await save_facts(current.id, facts) if facts else 0
    return {"extracted": len(facts), "saved": saved, "facts": facts}
