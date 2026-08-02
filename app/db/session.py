# -*- coding: utf-8 -*-
"""数据库会话与初始化。

采用 SQLAlchemy 2.0 异步引擎，与 FastAPI 的 async 路由天然契合。
开发用 SQLite（零安装），生产切 MySQL 只需改 DATABASE_URL。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import database_config

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


# 异步引擎（单例）
engine = create_async_engine(
    database_config.resolved_url,
    echo=database_config.echo,
    future=True,
)

# 异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供一个数据库会话，请求结束自动关闭。"""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """建表（开发用；生产应走 Alembic 迁移）。

    导入所有模型以注册到 Base.metadata，再统一 create_all。
    """
    # 导入模型触发注册（不可删）
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库已初始化: %s", database_config.resolved_url)
