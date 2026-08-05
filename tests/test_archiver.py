# -*- coding: utf-8 -*-
"""数据归档测试 - 借鉴 JavaGuide data-cold-hot-separation.md。

覆盖:
- archive_old_chat_messages: 删除 N 天前的消息
- archive_old_orders: 删除 N 天前的订单
- archive_old_data: 一次性跑所有归档
- 边界: 没有老数据 / 只有新数据 / 混合
"""
import asyncio
from datetime import datetime, timedelta
import pytest
from sqlalchemy import delete, select

from app.core.archiver import (
    archive_old_chat_messages, archive_old_orders, archive_old_data,
    DEFAULT_ARCHIVE_DAYS,
)
from app.db.models import ChatMessage, Order, User
from app.db.session import async_session_maker


# ===================================================================
# Fixtures
# ===================================================================

async def _ensure_user(user_id: int, name: str):
    """确保测试 user 存在。"""
    from app.auth.security import hash_password
    async with async_session_maker() as s:
        existing = (await s.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not existing:
            s.add(User(id=user_id, phone=f"arch{user_id}", name=name, password_hash=hash_password("test")))
            await s.commit()


async def _create_chat(user_id: int, days_ago: int) -> int:
    """创建一条 N 天前的 chat_message。Returns: id."""
    async with async_session_maker() as s:
        m = ChatMessage(
            user_id=user_id, role="user", content=f"msg {days_ago}d ago",
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m.id


async def _create_order(user_id: int, days_ago: int) -> int:
    """创建 N 天前的 order。"""
    async with async_session_maker() as s:
        from datetime import time, date
        o = Order(
            user_id=user_id,
            order_no=f"ARCH{datetime.now().strftime('%Y%m%d%H%M%S%f')}{user_id}",
            service_type="test",
            appointment_date=date.today() - timedelta(days=days_ago),
            appointment_time=time(10, 0),
            duration_minutes=60,
            total_price=100.0,
            status="completed",
            customer_phone="13800000000",
            customer_name="test",
            created_at=datetime.now() - timedelta(days=days_ago),
        )
        s.add(o)
        await s.commit()
        await s.refresh(o)
        return o.id


async def _cleanup():
    """清掉所有测试数据。"""
    async with async_session_maker() as s:
        await s.execute(delete(ChatMessage).where(ChatMessage.user_id.in_([9801, 9802, 9803])))
        await s.execute(delete(Order).where(Order.user_id.in_([9801, 9802, 9803])))
        await s.commit()


@pytest.fixture(autouse=True)
async def setup_users():
    await _ensure_user(9801, "arch_test_a")
    await _ensure_user(9802, "arch_test_b")
    await _ensure_user(9803, "arch_test_c")
    yield
    await _cleanup()


# ===================================================================
# 1. chat_messages 归档
# ===================================================================

@pytest.mark.asyncio
async def test_archive_chat_messages_basic():
    """30 天前的消息被归档 (阈值 30 天)。"""
    await _cleanup()
    old_id = await _create_chat(9801, days_ago=30)
    new_id = await _create_chat(9801, days_ago=10)
    # 阈值 30 天: 30 天前的应该被删
    deleted = await archive_old_chat_messages(days=30)
    assert deleted == 1
    # 验证
    async with async_session_maker() as s:
        assert (await s.execute(select(ChatMessage).where(ChatMessage.id == old_id))).scalar_one_or_none() is None
        assert (await s.execute(select(ChatMessage).where(ChatMessage.id == new_id))).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_archive_chat_messages_default_180_days():
    """默认 180 天阈值。"""
    await _cleanup()
    old_id = await _create_chat(9802, days_ago=181)
    new_id = await _create_chat(9802, days_ago=100)
    deleted = await archive_old_chat_messages()  # 默认 180 天
    assert deleted == 1
    # 100 天前的应该还在
    async with async_session_maker() as s:
        assert (await s.execute(select(ChatMessage).where(ChatMessage.id == new_id))).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_archive_chat_messages_no_old():
    """没有老数据时返回 0。"""
    await _cleanup()
    await _create_chat(9803, days_ago=10)
    deleted = await archive_old_chat_messages(days=30)
    assert deleted == 0


# ===================================================================
# 2. orders 归档
# ===================================================================

@pytest.mark.asyncio
async def test_archive_orders_basic():
    """30 天前的订单被归档。"""
    await _cleanup()
    old_id = await _create_order(9801, days_ago=30)
    new_id = await _create_order(9801, days_ago=10)
    deleted = await archive_old_orders(days=30)
    assert deleted == 1
    async with async_session_maker() as s:
        assert (await s.execute(select(Order).where(Order.id == old_id))).scalar_one_or_none() is None
        assert (await s.execute(select(Order).where(Order.id == new_id))).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_archive_orders_no_old():
    """没有老订单。"""
    await _cleanup()
    await _create_order(9802, days_ago=10)
    deleted = await archive_old_orders(days=30)
    assert deleted == 0


# ===================================================================
# 3. archive_old_data (一次性)
# ===================================================================

@pytest.mark.asyncio
async def test_archive_old_data_combined():
    """一次性归档 chat + orders。"""
    await _cleanup()
    old_chat = await _create_chat(9801, days_ago=200)
    new_chat = await _create_chat(9801, days_ago=10)
    old_order = await _create_order(9802, days_ago=200)
    new_order = await _create_order(9802, days_ago=10)
    result = await archive_old_data(days=180)
    assert result["chat_messages_deleted"] == 1
    assert result["orders_deleted"] == 1
    assert result["cutoff_days"] == 180
    # 验证新数据保留
    async with async_session_maker() as s:
        assert (await s.execute(select(ChatMessage).where(ChatMessage.id == new_chat))).scalar_one_or_none() is not None
        assert (await s.execute(select(Order).where(Order.id == new_order))).scalar_one_or_none() is not None


# ===================================================================
# 4. 批量删除 (避免大事务)
# ===================================================================

@pytest.mark.asyncio
async def test_archive_batched():
    """大批量删除用 batch (避免大事务锁表)。"""
    await _cleanup()
    # 插入 5 条老消息
    for _ in range(5):
        await _create_chat(9803, days_ago=200)
    # 用小 batch (2) 测试分批
    deleted = await archive_old_chat_messages(days=180, batch_size=2)
    assert deleted == 5  # 全部被删 (即使分批)
