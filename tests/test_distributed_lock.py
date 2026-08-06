# -*- coding: utf-8 -*-
"""分布式锁测试 (PG advisory_lock).

借鉴 JavaGuide distributed-lock.md.
"""
import asyncio
import pytest

from app.core.concurrency.lock import (
    advisory_lock, try_advisory_lock, key_to_bigint,
    LockNotAcquiredError, order_create_key, order_status_key,
)
from app.db.session import async_session_maker


# ===================================================================
# 工具函数
# ===================================================================

def test_key_to_bigint_string():
    k = key_to_bigint("test_key")
    assert isinstance(k, int)
    assert 0 <= k < 2**63


def test_key_to_bigint_consistent():
    k1 = key_to_bigint("hello")
    k2 = key_to_bigint("hello")
    assert k1 == k2


def test_key_to_bigint_int():
    k = key_to_bigint(12345)
    assert k == 12345


def test_key_to_bigint_different():
    assert key_to_bigint("a") != key_to_bigint("b")


def test_order_create_key_format():
    from datetime import time, date
    k = order_create_key(123, date(2026, 8, 5))
    assert k.startswith("order_create:123:")


def test_order_status_key_format():
    k = order_status_key(456)
    assert k == "order_status:456"


# ===================================================================
# advisory_lock 集成测试
# ===================================================================

@pytest.mark.asyncio
async def test_advisory_lock_basic():
    """基本获取和释放锁。"""
    async with async_session_maker() as s:
        async with advisory_lock(s, "test_lock_basic"):
            # 锁住中
            pass
        # 释放后
        # 应该能再获取
        async with advisory_lock(s, "test_lock_basic"):
            pass


@pytest.mark.asyncio
async def test_try_advisory_lock_success():
    """非阻塞锁 - 成功。"""
    async with async_session_maker() as s:
        async with try_advisory_lock(s, "test_try_lock_success"):
            pass


@pytest.mark.asyncio
async def test_try_advisory_lock_already_held():
    """非阻塞锁 - 锁被持有时立即失败。"""
    async with async_session_maker() as s1:
        async with advisory_lock(s1, "test_lock_held"):
            # 同一个 key, 另一个 session 拿不到
            async with async_session_maker() as s2:
                with pytest.raises(LockNotAcquiredError):
                    async with try_advisory_lock(s2, "test_lock_held"):
                        pass


@pytest.mark.asyncio
async def test_different_keys_no_conflict():
    """不同 key 不互锁。"""
    async with async_session_maker() as s1:
        async with advisory_lock(s1, "key_A_unique"):
            async with async_session_maker() as s2:
                # 不同 key 可以同时持有
                async with advisory_lock(s2, "key_B_unique"):
                    pass


@pytest.mark.asyncio
async def test_same_key_serial():
    """同 key 串行 (第二个等第一个释放)。"""
    execution_order = []

    async def task1():
        async with async_session_maker() as s:
            async with advisory_lock(s, "serial_test", timeout_ms=5000):
                await asyncio.sleep(0.2)
                execution_order.append("task1_done")

    async def task2():
        await asyncio.sleep(0.05)  # 错开启动
        async with async_session_maker() as s:
            async with advisory_lock(s, "serial_test", timeout_ms=5000):
                execution_order.append("task2_done")

    await asyncio.gather(task1(), task2())
    # task1 必须先完成 (持锁 0.2s, task2 等)
    assert execution_order == ["task1_done", "task2_done"]


@pytest.mark.asyncio
async def test_lock_released_after_exception():
    """异常时锁自动释放。"""
    with pytest.raises(ValueError):
        async with async_session_maker() as s:
            async with advisory_lock(s, "lock_exception_test"):
                raise ValueError("test")
    # 应该能立即再获取
    async with async_session_maker() as s:
        async with advisory_lock(s, "lock_exception_test", timeout_ms=100):
            pass


@pytest.mark.asyncio
async def test_timeout_returns_immediately():
    """非阻塞超时立即返回失败。"""
    async with async_session_maker() as s1:
        async with advisory_lock(s1, "timeout_test", timeout_ms=60000):
            async with async_session_maker() as s2:
                # try_advisory_lock 不阻塞, 立即失败
                with pytest.raises(LockNotAcquiredError):
                    async with try_advisory_lock(s2, "timeout_test"):
                        pass


# ===================================================================
# Order 锁辅助函数
# ===================================================================

def test_order_create_key_uniqueness():
    """同发型师不同时间 -> 不同 key。"""
    from datetime import time, date
    k1 = order_create_key(1, date(2026, 8, 5))
    k2 = order_create_key(1, date(2026, 8, 6))
    assert k1 != k2


def test_order_create_key_different_stylist():
    """同时段不同发型师 -> 不同 key。"""
    from datetime import time, date
    k1 = order_create_key(1, date(2026, 8, 5))
    k2 = order_create_key(2, date(2026, 8, 5))
    assert k1 != k2
