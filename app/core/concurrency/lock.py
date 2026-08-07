# -*- coding: utf-8 -*-
"""分布式锁：基于 PG advisory_lock，事务内自动释放。"""
from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def key_to_bigint(key: str | int) -> int:
    """把任意 key 转成 bigint (PG advisory lock 需要)。"""
    if isinstance(key, int):
        return key % (2**63)
    h = hashlib.md5(str(key).encode()).hexdigest()
    # 取前 16 hex 字符 = 64 bit (PG advisory lock 限制)
    return int(h[:15], 16) % (2**63)


@asynccontextmanager
async def advisory_lock(session: AsyncSession, key: str | int, timeout_ms: int = 5000):
    """阻塞获取 PG advisory lock (事务内自动释放)。

    Args:
        session: 异步 DB session
        key: 锁 key (字符串或整数, 自动 hash)
        timeout_ms: 等待超时 (毫秒)

    Raises:
        TimeoutError: 超时未获取到锁
    """
    bigint_key = key_to_bigint(key)
    # pg_advisory_lock (阻塞, 不会超时)
    # pg_try_advisory_lock (非阻塞, 立即返回)
    # pg_advisory_xact_lock (事务结束自动释放)
    if timeout_ms > 0:
        # 用 SET LOCAL lock_timeout 限制等待时间
        await session.execute(text(f"SET LOCAL lock_timeout = '{timeout_ms}ms'"))
    await session.execute(text("SELECT pg_advisory_lock(:k)"), {"k": bigint_key})
    try:
        yield
    finally:
        # 显式释放 (即使事务结束也会自动释放)
        try:
            await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": bigint_key})
        except Exception:
            pass  # 事务回滚时自动释放


@asynccontextmanager
async def try_advisory_lock(session: AsyncSession, key: str | int):
    """非阻塞获取 PG advisory lock。

    失败立即抛 LockNotAcquiredError。
    """
    bigint_key = key_to_bigint(key)
    result = await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": bigint_key})
    acquired = result.scalar()
    if not acquired:
        raise LockNotAcquiredError(f"Failed to acquire lock: {key}")
    try:
        yield
    finally:
        try:
            await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": bigint_key})
        except Exception:
            pass


class LockNotAcquiredError(Exception):
    """锁获取失败 (非阻塞模式)。"""
    pass


# 订单锁专用 key
def order_create_key(stylist_id: int, appointment_time) -> str:
    """订单创建锁 key: 同发型师 + 同时段防重复。"""
    return f"order_create:{stylist_id}:{appointment_time.isoformat()}"


def order_status_key(order_id: int) -> str:
    """订单状态机锁 key: 防并发改。"""
    return f"order_status:{order_id}"
