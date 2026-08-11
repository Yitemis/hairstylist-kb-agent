# -*- coding: utf-8 -*-
"""permission 路由 (从 api.py 拆出)。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user
from app.db.session import get_session

router = APIRouter(prefix="/api", tags=["permission"])


@router.post("/permission/evaluate", summary="评估工具调用权限")
async def evaluate_permission(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """评估一个工具调用是否需要用户确认（借鉴 AgentScope PermissionEngine）。

    Body: { "tool_name": str, "tool_args": dict, "context": dict }
    Returns: { "decision": "allowed"|"asking"|"denied", "ask_id": str, "ask_message": str, ... }
    """
    from app.core.permission import (
        PermissionRequest, get_permission_engine,
    )
    request = PermissionRequest(
        user_id=current.id,
        tool_name=body.get("tool_name", ""),
        tool_args=body.get("tool_args") or {},
        context=body.get("context") or {},
    )
    engine = get_permission_engine()
    result = engine.evaluate(request)

    response = {
        "decision": result.decision.value,
        "reason": result.reason,
        "ask_message": result.ask_message,
        "deny_message": result.deny_message,
    }

    if result.decision.value == "asking":
        ask_id = engine.create_pending_ask(request, result)
        response["ask_id"] = ask_id

    return response


@router.post("/permission/resolve", summary="确认/拒绝 pending 询问")
async def resolve_permission(
    body: dict,
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """用户在前端点击"确认"或"拒绝"后，调用此端点。

    Body: { "ask_id": str, "approved": bool }
    """
    from app.core.permission import get_permission_engine
    engine = get_permission_engine()
    ask_id = body.get("ask_id")
    approved = bool(body.get("approved"))
    if not ask_id:
        raise HTTPException(status_code=400, detail="ask_id 必填")
    result = engine.resolve_ask(ask_id, approved)
    if result is None:
        raise HTTPException(status_code=404, detail="ask_id 不存在或已过期")
    request, perm_result = result
    return {
        "decision": perm_result.decision.value,
        "tool_name": request.tool_name,
        "tool_args": request.tool_args,
        "approved": approved,
    }


# ============================================================
# 技能库 API（HarnessAgent 招牌能力）
# ============================================================


