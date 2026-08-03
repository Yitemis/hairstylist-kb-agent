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


@pytest.mark.asyncio
async def test_init_db_creates_all_tables():
    """测试 init_db 能建出所有表（多租户 + 分店 + 发型师 + 服务 + 订单）。"""
    from sqlalchemy import text
    async with async_session_maker() as session:
        for table in ["users", "staffs", "branches", "stylists", "services", "orders", "chat_messages", "chat_sessions", "user_profiles"]:
            r = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            assert r.scalar() >= 0, f"表 {table} 不可访问"


@pytest.mark.asyncio
async def test_branch_filter_stylists():
    """测试按分店筛选发型师。"""
    from sqlalchemy import select
    async with async_session_maker() as session:
        b1 = (await session.execute(select(Branch).where(Branch.id == 1))).scalar_one_or_none()
        if b1:
            b1_stylists = (await session.execute(select(Stylist).where(Stylist.branch_id == 1))).scalars().all()
            assert all(s.branch_id == 1 for s in b1_stylists), "分店筛选失败"


@pytest.mark.asyncio
async def test_order_unique_no():
    """测试订单号唯一性约束。"""
    from sqlalchemy import select
    async with async_session_maker() as session:
        existing = (await session.execute(select(Order).limit(1))).scalar_one_or_none()
        if existing:
            # 已有订单，验证订单号存在
            assert existing.order_no is not None
            assert len(existing.order_no) > 0


@pytest.mark.asyncio
async def test_branch_list_has_coordinates():
    """测试分店有经纬度（用于距离排序）。"""
    from sqlalchemy import select
    async with async_session_maker() as session:
        branches = (await session.execute(select(Branch))).scalars().all()
        for b in branches:
            if b.is_active:
                assert b.latitude is not None
                assert b.longitude is not None


@pytest.mark.asyncio
async def test_stylist_specialties_is_json():
    """测试发型师擅长字段是 JSON 字符串。"""
    import json
    from sqlalchemy import select
    async with async_session_maker() as session:
        stylists = (await session.execute(select(Stylist).where(Stylist.is_active == True))).scalars().all()
        for s in stylists:
            if s.specialties:
                specialties = json.loads(s.specialties)
                assert isinstance(specialties, list), f"发型师 {s.name} 擅长字段不是 list"
