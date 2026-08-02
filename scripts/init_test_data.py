#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化数据库表 + 测试数据：分店、发型师、服务。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio

from app.db.session import async_session_maker, init_db
from app.db.models import Branch, Stylist, Service


async def init_test_data() -> None:
    async with async_session_maker() as session:
        # 1. 两家分店
        branches = [
            Branch(
                name="人民广场店",
                address="上海市黄浦区人民大道1号",
                phone="021-12345678",
                description="市中心旗舰店，环境优雅",
                latitude=31.2304,
                longitude=121.4737,
                max_daily_appointments=20,
                is_active=True,
            ),
            Branch(
                name="徐家汇店",
                address="上海市徐汇区虹桥路1号",
                phone="021-87654321",
                description="商圈分店，交通便利",
                latitude=31.1960,
                longitude=121.4365,
                max_daily_appointments=15,
                is_active=True,
            ),
            Branch(
                name="陆家嘴店",
                address="上海市浦东新区陆家嘴环路1号",
                phone="021-11112222",
                description="高端商务区店",
                latitude=31.2390,
                longitude=121.4990,
                max_daily_appointments=18,
                is_active=True,
            ),
        ]
        for b in branches:
            session.add(b)
        await session.commit()
        print("插入 3 家分店")

        # 2. 4 位发型师（每个分店分配一些）
        stylists = [
            Stylist(
                branch_id=1,  # 人民广场
                name="张托尼",
                specialties='["烫发", "染发", "造型"]',
                description="10年高级发型师，擅长数码烫和时尚染色",
                max_daily_hours=8,
                is_active=True,
            ),
            Stylist(
                branch_id=1,  # 人民广场
                name="李大卫",
                specialties='["剪发", "护理"]',
                description="8年经验，剪发高手",
                max_daily_hours=8,
                is_active=True,
            ),
            Stylist(
                branch_id=2,  # 徐家汇
                name="王芳",
                specialties='["染发", "造型"]',
                description="6年经验，色彩感强",
                max_daily_hours=8,
                is_active=True,
            ),
            Stylist(
                branch_id=3,  # 陆家嘴
                name="陈丽",
                specialties='["烫发", "护理", "造型"]',
                description="5年经验，专注烫发护理",
                max_daily_hours=8,
                is_active=True,
            ),
        ]
        for s in stylists:
            session.add(s)
        await session.commit()
        print("插入 4 位发型师")

        # 3. 5 个服务项目
        services = [
            Service(
                name="精剪（女）",
                category="剪发",
                duration_minutes=60,
                price=128.0,
                description="专业女士精剪，包含吹干造型",
                is_active=True,
            ),
            Service(
                name="精剪（男）",
                category="剪发",
                duration_minutes=45,
                price=88.0,
                description="男士精剪",
                is_active=True,
            ),
            Service(
                name="数码烫",
                category="烫发",
                duration_minutes=180,
                price=580.0,
                description="韩式大波浪烫，自然蓬松",
                is_active=True,
            ),
            Service(
                name="全头染",
                category="染发",
                duration_minutes=120,
                price=460.0,
                description="全头单色染",
                is_active=True,
            ),
            Service(
                name="角蛋白护理",
                category="护理",
                duration_minutes=90,
                price=280.0,
                description="深层修复受损发质",
                is_active=True,
            ),
        ]
        for sv in services:
            session.add(sv)
        await session.commit()
        print("插入 5 个服务项目")


async def main():
    print("初始化数据库表结构...")
    await init_db()
    print("插入测试数据...")
    await init_test_data()
    print("\n数据库初始化完成！")


if __name__ == "__main__":
    asyncio.run(main())
