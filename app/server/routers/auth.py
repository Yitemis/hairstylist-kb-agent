# -*- coding: utf-8 -*-
"""认证路由：注册 / 登录 / 登出 / 当前用户。

用户(users)与店家(staffs)分表存储，通过 role 区分登录目标表。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import Staff, User
from app.db.session import get_session
from app.schemas.auth import (
    StaffLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _model_for_role(role: str):
    """按角色返回对应的 ORM 模型类。"""
    return Staff if role == "staff" else User


@router.post("/register", response_model=TokenResponse, summary="注册")
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """注册新账号（手机号 + 密码）。"""
    model = _model_for_role(body.role)

    exists = await session.scalar(select(model).where(model.phone == body.phone))
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")

    # staff 默认角色 worker；user 固定 user
    account = model(
        phone=body.phone,
        password_hash=hash_password(body.password),
        name=body.name,
        role="worker" if body.role == "staff" else "user",
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    token = create_access_token(
        subject=account.id, role=account.role, extra={"name": account.name}
    )
    return TokenResponse(access_token=token, user=UserPublic.model_validate(account))


@router.post("/login", response_model=TokenResponse, summary="登录")
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """手机号 + 密码登录。role 决定查 users 还是 staffs 表。"""
    model = _model_for_role(body.role)

    account = await session.scalar(select(model).where(model.phone == body.phone))
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="手机号或密码错误"
        )

    token = create_access_token(
        subject=account.id, role=account.role, extra={"name": account.name}
    )
    return TokenResponse(access_token=token, user=UserPublic.model_validate(account))




@router.post("/staff/login", response_model=TokenResponse, summary="员工登录")
async def staff_login(
    body: StaffLoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """员工登录：查 staffs 表 (员工)，返回 role='admin'。

    解决 AdminGuard 拒绝 'worker' role 的问题：员工登录后强制 role='admin'。
    """
    from app.db.models import Staff
    from app.auth.security import verify_password, create_access_token
    
    staff = await session.scalar(select(Staff).where(Staff.phone == body.phone))
    if staff is None or not verify_password(body.password, staff.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="手机号或密码错误"
        )
    # 强制 admin role (Staff 默认是 worker, 但登录后赋予 admin 权限)
    token = create_access_token(
        subject=staff.id, role="admin", extra={"name": staff.name, "is_staff": True}
    )
    # 返回 role='admin' (强制覆盖)
    user_dict = {
        "id": staff.id, "phone": staff.phone, "name": staff.name,
        "role": "admin", "avatar": getattr(staff, 'avatar', None),
    }
    return TokenResponse(access_token=token, user=user_dict)



@router.post("/logout", summary="登出")
async def logout(
    _current: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """登出。JWT 无状态，前端删除 token 即可；此处仅作语义接口。"""
    return {"status": "ok", "message": "已登出"}


@router.get("/me", response_model=UserPublic, summary="当前用户")
async def me(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserPublic:
    """返回当前登录用户的完整信息。"""
    model = Staff if current.is_staff else User
    account = await session.get(model, current.id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return UserPublic.model_validate(account)
