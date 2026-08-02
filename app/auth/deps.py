# -*- coding: utf-8 -*-
"""FastAPI 认证依赖：从 Bearer Token 解析当前登录主体。

- get_current_user  → 任意已登录主体（含 user / staff）
- require_staff      → 仅店家/员工可访问（订单后台、知识库管理）
- require_user       → 仅 C 端用户可访问（下单）
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import decode_token

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """当前登录主体（从 JWT 解析，不查库，轻量）。"""

    def __init__(self, user_id: int, role: str, claims: dict) -> None:
        self.id = user_id
        self.role = role
        self.claims = claims

    @property
    def is_staff(self) -> bool:
        return self.role in ("staff", "admin", "worker")

    @property
    def is_user(self) -> bool:
        return self.role == "user"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """解析 Authorization: Bearer <token>，返回当前主体。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        user_id=int(payload["sub"]),
        role=payload.get("role", "user"),
        claims=payload,
    )


async def require_staff(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """仅允许店家/员工。"""
    if not current.is_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要店家权限")
    return current


async def require_user(
    current: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """仅允许 C 端用户。"""
    if not current.is_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要用户权限")
    return current
