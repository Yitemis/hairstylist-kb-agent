"""定期更新 Gauge 指标（如 memory_facts_total、active_sessions）。

借鉴 12-factor app：进程内异步后台任务，无需外部 cron。
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def update_gauge_loop(interval_seconds: int = 60):
    """定期刷新 Gauge 指标（每 60s）。"""
    while True:
        try:
            # 1. memory_facts_total: 查 user_profiles 表
            try:
                from app.core.metrics import memory_facts_total
                from app.db.session import async_session_maker
                from sqlalchemy import text

                async with async_session_maker() as session:
                    rows = (await session.execute(
                        text("SELECT user_id, COUNT(*) FROM user_profiles GROUP BY user_id")
                    )).fetchall()
                    # 清掉旧标签 (避免 label cardinality 增长)
                    memory_facts_total.clear()
                    for user_id, count in rows:
                        memory_facts_total.labels(user_id=str(user_id)).set(count)
            except Exception as e:
                logger.debug("memory_facts gauge update failed: %s", e)

        except Exception as e:
            logger.warning("Gauge update loop error: %s", e)
        await asyncio.sleep(interval_seconds)


def start_metrics_updater(loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
    """在 lifespan 启动时调用。"""
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
    return loop.create_task(update_gauge_loop())
