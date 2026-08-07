# -*- coding: utf-8 -*-
"""数据归档：定期清理 6 个月前的冷数据，释放 PG 空间。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select

from app.core.metrics import (
    chat_requests_total,  # 复用 metrics
)
from app.db.models import ChatMessage, Order
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)


# 归档阈值（天）
DEFAULT_ARCHIVE_DAYS = 180


async def archive_old_chat_messages(days: int = DEFAULT_ARCHIVE_DAYS, batch_size: int = 1000) -> int:
    """归档 6 个月前的 chat_messages。

    简化策略：先 DELETE 老消息（生产应该移到 archive 表 + S3）。
    Returns: 删除的消息数。
    """
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    async with async_session_maker() as s:
        # 分批删（避免大事务）- SQLAlchemy Delete 不支持 limit，用 subquery
        while True:
            subq = select(ChatMessage.id).where(
                ChatMessage.created_at < cutoff
            ).limit(batch_size).scalar_subquery()
            stmt = delete(ChatMessage).where(ChatMessage.id.in_(subq))
            result = await s.execute(stmt)
            await s.commit()
            deleted += result.rowcount
            if result.rowcount < batch_size:
                break
    if deleted > 0:
        logger.info("Archived %d old chat_messages (>%d days)", deleted, days)
    return deleted


async def archive_old_orders(days: int = DEFAULT_ARCHIVE_DAYS, batch_size: int = 1000) -> int:
    """归档 6 个月前的 orders。

    简化策略：直接 DELETE 老订单（生产应该移到 archive_orders 表 + S3）。
    Returns: 删除的订单数。
    """
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    async with async_session_maker() as s:
        # 分批删（避免大事务）
        while True:
            subq = select(Order.id).where(
                Order.created_at < cutoff
            ).limit(batch_size).scalar_subquery()
            stmt = delete(Order).where(Order.id.in_(subq))
            result = await s.execute(stmt)
            await s.commit()
            deleted += result.rowcount
            if result.rowcount < batch_size:
                break
    if deleted > 0:
        logger.info("Archived %d old orders (>%d days)", deleted, days)
    return deleted


async def archive_old_data(days: int = DEFAULT_ARCHIVE_DAYS) -> dict:
    """一次性跑所有归档。

    Returns: 各类删除数。
    """
    chat_count = await archive_old_chat_messages(days=days)
    order_count = await archive_old_orders(days=days)
    return {
        "chat_messages_deleted": chat_count,
        "orders_deleted": order_count,
        "cutoff_days": days,
        "run_at": datetime.now().isoformat(),
    }


async def archive_loop(interval_hours: int = 24):
    """定期归档循环（每天 1 次）。"""
    # 启动时先跑一次
    try:
        result = await archive_old_data()
        logger.info("Initial archive done: %s", result)
    except Exception as e:
        logger.error("Initial archive failed: %s", e)
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            result = await archive_old_data()
            logger.info("Scheduled archive done: %s", result)
        except Exception as e:
            logger.error("Scheduled archive failed: %s", e)


def start_archiver(loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
    """在 lifespan 启动时调用。"""
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
    return loop.create_task(archive_loop())


# Prometheus 指标 - 归档相关
from prometheus_client import Counter
ARCHIVED_CHAT_MESSAGES = Counter(
    "archived_chat_messages_total",
    "Total chat messages archived"
)
ARCHIVED_ORDERS = Counter(
    "archived_orders_total",
    "Total orders archived"
)
