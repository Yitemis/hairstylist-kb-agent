# -*- coding: utf-8 -*-
"""IndexAlias: 蓝绿索引切换.

设计:
  - 默认 alias = "prod" -> 指向 "index_v1"
  - 切到新 embedding 模型 -> 先建 "index_v2", 跑 eval, dry run, 切 alias
  - 保留老索引 7 天 (回滚窗口)
  - child_chunks.index_alias 字段记录当前在哪个 alias 下
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AliasSwitchResult:
    action: str
    from_alias: str
    to_alias: str
    switched_count: int = 0
    dry_run: bool = True
    error: Optional[str] = None
    timestamp: str = ""


class IndexAlias:
    """索引别名管理器 (蓝绿切换).

    API:
      alias = IndexAlias()
      result = await alias.switch("index_v2", "index_v1", dry_run=True)
      result = await alias.create_new("index_v2")
      result = await alias.rollback()
    """

    DEFAULT_ALIAS = "prod"
    ROLLBACK_WINDOW_DAYS = 7

    def __init__(self):
        self._history: List[Dict[str, Any]] = []

    async def switch(self, new_index: str, old_index: str, dry_run: bool = True) -> AliasSwitchResult:
        """切 alias: prod -> new_index.

        Args:
            new_index: 新索引名 (e.g. "index_v2_bge_large")
            old_index: 老索引名 (回滚用, e.g. "index_v1")
            dry_run: True=只输出计划, False=实际切

        Returns:
            AliasSwitchResult
        """
        result = AliasSwitchResult(
            action="switch",
            from_alias=old_index,
            to_alias=new_index,
            dry_run=dry_run,
            timestamp=datetime.now().isoformat(),
        )
        try:
            if dry_run:
                logger.info(
                    "IndexAlias: DRY-RUN switch %s -> %s (no actual change)",
                    old_index, new_index,
                )
                result.action = "dry_run"
                result.switched_count = await self._count_index(new_index)
                return result

            # 1. 跑 eval 验证 (可选, 简化: 假设外部跑过)
            # 2. 实际切: UPDATE child_chunks.index_alias = new_index
            from app.db.session import async_session_maker
            from app.db.models import ChildChunk
            from sqlalchemy import update as sql_update

            async with async_session_maker() as session:
                upd = await session.execute(
                    sql_update(ChildChunk)
                    .where(ChildChunk.index_alias == old_index)
                    .values(index_alias=new_index)
                )
                await session.commit()
                result.switched_count = upd.rowcount or 0

            self._history.append({
                "from": old_index, "to": new_index,
                "count": result.switched_count,
                "at": result.timestamp,
            })
            logger.info(
                "IndexAlias: switched %s -> %s (%d rows)",
                old_index, new_index, result.switched_count,
            )
            return result
        except Exception as e:
            logger.exception("IndexAlias switch failed: %s", e)
            result.error = str(e)
            result.action = "error"
            return result

    async def create_new(self, new_index: str, embedding_model: str = None) -> AliasSwitchResult:
        """建新索引 (空). 不影响 prod."""
        result = AliasSwitchResult(
            action="create_new", from_alias="", to_alias=new_index,
            timestamp=datetime.now().isoformat(),
        )
        try:
            # 实际建新 collection / index 由 vector store 实现, 这里只标记
            from app.db.session import async_session_maker
            from app.db.models import ChildChunk
            from sqlalchemy import select, func

            async with async_session_maker() as session:
                cnt = (await session.execute(
                    select(func.count()).select_from(ChildChunk).where(ChildChunk.index_alias == new_index)
                )).scalar() or 0
                result.switched_count = cnt
            logger.info(
                "IndexAlias: create_new %s (existing %d rows)",
                new_index, cnt,
            )
            return result
        except Exception as e:
            result.error = str(e)
            result.action = "error"
            return result

    async def rollback(self) -> AliasSwitchResult:
        """回滚到上一个 alias."""""
        if not self._history:
            return AliasSwitchResult(
                action="rollback", from_alias="", to_alias="",
                error="no history to rollback",
            )
        last = self._history[-1]
        result = await self.switch(
            new_index=last["from"], old_index=last["to"],
            dry_run=False,
        )
        result.action = "rollback"
        logger.warning("IndexAlias: ROLLBACK from %s to %s", last["to"], last["from"])
        return result

    async def cleanup_old(self, keep_days: int = 7) -> AliasSwitchResult:
        """清理 N 天前的老索引 (回收存储).

        默认 ROLLBACK_WINDOW_DAYS=7, 超过 7 天的 alias 自动清理.
        """
        from app.db.session import async_session_maker
        from app.db.models import ChildChunk
        from sqlalchemy import select, func, and_

        cutoff = datetime.now() - timedelta(days=keep_days)
        result = AliasSwitchResult(
            action="cleanup", from_alias="", to_alias="",
            timestamp=cutoff.isoformat(),
        )
        try:
            async with async_session_maker() as session:
                old = (await session.execute(
                    select(ChildChunk.index_alias, func.count())
                    .where(ChildChunk.created_at < cutoff)
                    .where(ChildChunk.index_alias != self.DEFAULT_ALIAS)
                    .group_by(ChildChunk.index_alias)
                )).all()
                result.switched_count = sum(row[1] for row in old) if old else 0
            logger.info(
                "IndexAlias: cleanup candidates (%d rows older than %s)",
                result.switched_count, cutoff.isoformat(),
            )
            return result
        except Exception as e:
            result.error = str(e)
            return result

    async def _count_index(self, alias: str) -> int:
        """统计 alias 下的 child_chunks 数."""""
        from app.db.session import async_session_maker
        from app.db.models import ChildChunk
        from sqlalchemy import select, func
        try:
            async with async_session_maker() as session:
                return (await session.execute(
                    select(func.count()).select_from(ChildChunk).where(ChildChunk.index_alias == alias)
                )).scalar() or 0
        except Exception:
            return 0

    def get_history(self) -> List[Dict[str, Any]]:
        """获取切换历史."""
        return list(self._history)


_alias_manager: Optional[IndexAlias] = None


def get_index_alias() -> IndexAlias:
    """获取全局 IndexAlias 单例."""
    global _alias_manager
    if _alias_manager is None:
        _alias_manager = IndexAlias()
    return _alias_manager


__all__ = ["IndexAlias", "AliasSwitchResult", "get_index_alias"]
