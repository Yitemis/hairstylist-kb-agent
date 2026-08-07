# -*- coding: utf-8 -*-
"""请求幂等：基于 Idempotency-Key 防重复扣费/重复处理。"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db.models import IdempotencyRecord
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = 24


def _hash_body(body: bytes) -> str:
    """Hash request body for comparison (prevent key reuse with different body)."""
    return hashlib.sha256(body).hexdigest()[:32]


async def get_idempotency_record(key: str) -> IdempotencyRecord | None:
    """从 DB 查幂等记录（同时检查过期）。"""
    from sqlalchemy import select
    async with async_session_maker() as s:
        stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == key)
        rec = (await s.execute(stmt)).scalar_one_or_none()
    if rec and rec.expires_at < datetime.now():
        # 已过期 - 视为不存在（应该清理）
        return None
    return rec


async def save_idempotency_record(
    key: str,
    user_id: int,
    action: str,
    request_hash: str,
    response_status: int,
    response_body: dict,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> IdempotencyRecord:
    """保存幂等记录。"""
    async with async_session_maker() as s:
        rec = IdempotencyRecord(
            key=key,
            user_id=user_id,
            action=action,
            request_hash=request_hash,
            response_status=response_status,
            response_body=response_body,
            expires_at=datetime.now() + timedelta(hours=ttl_hours),
        )
        s.add(rec)
        await s.commit()
        await s.refresh(rec)
    return rec


def idempotent(action: str, ttl_hours: int = DEFAULT_TTL_HOURS):
    """幂等装饰器：从 Idempotency-Key header 取 key，命中则返回缓存。

    Args:
        action: 操作类型（如 "create_order"）
        ttl_hours: 幂等记录 TTL（默认 24h）

    要求：
    - 端点必须接受 Idempotency-Key header
    - user_id 从 current user 拿（依赖 require_user）
    - 重复请求 body 必须一致（hash 一致才返回缓存）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 1. 提取 Idempotency-Key
            request: Request = kwargs.get("request")
            if request is None:
                # 兜底：从 args 找 Request
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if request is None:
                # 没 Request - 不做幂等（避免破坏其他端点）
                return await func(*args, **kwargs)

            idem_key = request.headers.get("Idempotency-Key")
            if not idem_key:
                # 客户端没传 key - 不做幂等（强制要求）
                raise HTTPException(
                    status_code=400,
                    detail="Missing Idempotency-Key header. Please provide UUID v4.",
                )

            # 2. 取 user_id (从 kwargs.current)
            current = kwargs.get("current")
            if current is None:
                # 没 current - 不做幂等
                return await func(*args, **kwargs)
            user_id = current.id

            # 3. 查已存在的幂等记录
            existing = await get_idempotency_record(idem_key)
            if existing is not None:
                # 验证 body hash 一致（防 key 复用但 body 不同）
                body = await request.body()
                body_hash = _hash_body(body)
                if existing.request_hash != body_hash:
                    raise HTTPException(
                        status_code=422,
                        detail="Idempotency-Key reuse with different body. Use new key.",
                    )
                # 返回缓存的响应
                logger.info("Idempotency hit: key=%s user=%d", idem_key[:8], user_id)
                return JSONResponse(
                    content=existing.response_body,
                    status_code=existing.response_status,
                )

            # 4. 实际执行
            result = await func(*args, **kwargs)

            # 5. 保存结果（仅当 result 是 JSONResponse 或 dict）
            try:
                body = await request.body()
                body_hash = _hash_body(body)
                if isinstance(result, JSONResponse):
                    status_code = result.status_code
                    body_dict = json.loads(result.body.decode("utf-8") if isinstance(result.body, bytes) else result.body)
                elif isinstance(result, dict):
                    status_code = 200
                    body_dict = result
                else:
                    # Pydantic model
                    status_code = 200
                    body_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                await save_idempotency_record(
                    key=idem_key, user_id=user_id, action=action,
                    request_hash=body_hash, response_status=status_code,
                    response_body=body_dict, ttl_hours=ttl_hours,
                )
            except Exception as e:
                # 保存失败不影响主流程
                logger.warning("Failed to save idempotency record: %s", e)

            return result
        return wrapper
    return decorator


async def cleanup_expired_idempotency() -> int:
    """清理过期的幂等记录（定时任务调用）。"""
    from sqlalchemy import delete
    async with async_session_maker() as s:
        stmt = delete(IdempotencyRecord).where(
            IdempotencyRecord.expires_at < datetime.now()
        )
        result = await s.execute(stmt)
        await s.commit()
    return result.rowcount
