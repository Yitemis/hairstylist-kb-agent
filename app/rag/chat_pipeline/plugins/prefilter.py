# -*- coding: utf-8 -*-
"""PrefilterPlugin: tenant / audience / version 预过滤.

职责:
  1. 默认 audience_filter = ['user', 'all'] (C 端用户)
  2. tenant_id 从 user_id 派生 (这里已经是 ctx.user_id)
  3. category_filter 从 selfquery 已提取
  4. include_unpublished 强制 False (admin 显式 True)
  5. 任何空 filter 自动补默认
"""
from __future__ import annotations

import logging

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class PrefilterPlugin(Plugin):
    """预过滤 Plugin.

    priority=30
    """

    name = "prefilter"
    priority = 30

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        # 默认 audience filter (C 端用户)
        if not ctx.audience_filter:
            ctx.audience_filter = ["user", "all"]

        # 不允许 C 端用户看未发布
        if ctx.role not in ("admin", "staff", "auditor") and ctx.include_unpublished:
            logger.warning(
                "Prefilter: role=%s force include_unpublished=False",
                ctx.role,
            )
            ctx.include_unpublished = False

        # 排除 refuse 路径
        if ctx.gate_decision == "refuse":
            return ctx

        logger.info(
            "Prefilter: tenant=user_%d audience=%s category=%s published_only=%s",
            ctx.user_id, ctx.audience_filter, ctx.category_filter,
            not ctx.include_unpublished,
        )
        return ctx


__all__ = ["PrefilterPlugin"]
