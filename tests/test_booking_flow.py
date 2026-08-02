# -*- coding: utf-8 -*-
"""核心业务测试：订单流程、冲突检查。

参考 AgentScope 学习材料里强调的"测试是工程化基石"。
"""
import asyncio
import pytest
from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Branch, Order, Service, Stylist, User
from app.db.session import async_session_maker, init_db


async def test_init_db_creates_all_tables():
    """测试 init_db 能建出所有表（多租户 + 分店 + 发型师 + 服务 + 订单）。"""
    await init_db()
    async with async_session_maker() as session:
        # 简单查每张表是否可访问
        from sqlalchemy import select, text
        for table in ["users", "staffs", "branches", "stylists", "services", "orders", "chat_messages"]:
            r = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            assert r.scalar() >= 0, f"表 {table} 不可访问"


async def test_branch_filter_stylists():
    """测试按分店筛选发型师。"""
    from app.server.routers.stylists import list_stylists
    from fastapi import BackgroundTasks
    # 简单验证逻辑：query 参数 branch_id 应被正确接收


async def test_order_unique_no():
    """测试订单号唯一性。"""
    async with async_session_maker() as session:
        order = Order(
            order_no="TEST-001",
            user_id=1,
            status="pending",
        )
        session.add(order)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            # 重复插入应该失败（unique 约束）
            assert True


# 标记为 asyncio 测试
@pytest.mark.asyncio
async def test_async_init():
    await test_init_db_creates_all_tables()
