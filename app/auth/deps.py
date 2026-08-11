# -*- coding: utf-8 -*-
"""FastAPI 认证依赖：从 Bearer Token 或 HttpOnly Cookie 解析当前登录主体。

P1-4: 同时支持 Authorization header + access_token cookie（XSS-safe）。
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
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
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """解析 token：优先 Authorization header，fallback 到 access_token cookie (P1-4)。"""
    token: Optional[str] = None
    if credentials is not None:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
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
