# -*- coding: utf-8 -*-
"""工具调用审计 (P0-3: B 端管理 agent).

每个工具调用前: 记录到 tool_audit_log 表.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import insert

from app.db.models import ToolAuditLog
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)


async def log_tool_call(
    actor_id: int,
    actor_type: str,            # "staff" | "user" | "admin"
    tool_name: str,
    tool_args: Any,
    tool_result: Any,
    permission: str,             # "allowed" | "asking" | "denied"
    intent: Optional[str] = None,
    session_id: Optional[str] = None,
    user_message: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """异步写一条审计日志 (失败不影响主流程)."""
    try:
        args_str = json.dumps(tool_args, ensure_ascii=False, default=str)[:2000] if tool_args else None
        result_str = json.dumps(tool_result, ensure_ascii=False, default=str)[:1000] if tool_result else None
        msg_str = user_message[:500] if user_message else None
        async with async_session_maker() as session:
            stmt = insert(ToolAuditLog).values(
                actor_id=actor_id,
                actor_type=actor_type,
                tool_name=tool_name,
                tool_args=args_str,
                tool_result=result_str,
                permission=permission,
                intent=intent,
                session_id=session_id,
                user_message=msg_str,
                ip_address=ip_address,
            )
            await session.execute(stmt)
            await session.commit()
        logger.info(
            "AUDIT: %s actor=%s:%s tool=%s perm=%s",
            intent, actor_type, actor_id, tool_name, permission,
        )
    except Exception as e:
        # 审计失败不能影响主流程
        logger.warning("audit log failed: %s", e)
