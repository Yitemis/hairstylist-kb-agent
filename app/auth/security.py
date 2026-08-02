# -*- coding: utf-8 -*-
"""安全原语：密码哈希（bcrypt）+ JWT 令牌签发/校验。

直接用 bcrypt 包，避开 passlib 在 bcrypt 5.x 上的不兼容问题。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import auth_config


def hash_password(plain: str) -> str:
    """明文密码 → bcrypt 哈希。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    role: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 JWT。

    Args:
        subject: 用户主键 ID。
        role: 角色（user / staff / admin ...），用于前端路由与后端鉴权。
        extra: 附加声明（如姓名）。
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=auth_config.access_token_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, auth_config.jwt_secret, algorithm=auth_config.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    """校验并解析 JWT，失败返回 None。"""
    try:
        return jwt.decode(
            token,
            auth_config.jwt_secret,
            algorithms=[auth_config.jwt_algorithm],
        )
    except JWTError:
        return None
