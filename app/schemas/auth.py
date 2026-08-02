# -*- coding: utf-8 -*-
"""认证相关的请求/响应模型。"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class RegisterRequest(BaseModel):
    """注册请求。"""

    phone: str = Field(..., description="中国大陆手机号")
    password: str = Field(..., min_length=6, max_length=64, description="密码，至少 6 位")
    name: str = Field(..., min_length=1, max_length=50, description="姓名/昵称")
    role: Literal["user", "staff"] = Field("user", description="user=顾客, staff=店家")

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("手机号格式不正确")
        return v


class LoginRequest(BaseModel):
    """登录请求。"""

    phone: str
    password: str
    role: Literal["user", "staff"] = Field("user", description="登录身份")


class UserPublic(BaseModel):
    """对外暴露的用户信息（不含密码哈希）。"""

    id: int
    phone: str
    name: str
    role: str
    avatar: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """登录/注册成功响应。"""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic
