# -*- coding: utf-8 -*-
"""Tool 权限分级 + 装饰器.

借鉴 JavaGuide §5.6 "AI 工作流的安全风险"：
- 工具调用权限越界：删除/发送未授权 → 最小权限、高危操作 HITL
- 凡是会改数据 / 发请求 / 删除文件的任务，自由度都要收紧

借鉴 JavaGuide §2.1 L6 "约束、校验与恢复层"：
- 工具权限分级（读 / 写 / 发 / 删，每级独立授权）
- 高危操作 HITL 拦截

权限等级（从低到高）：
- READ：只读操作（搜索、列表）
- WRITE：写入但可撤销（创建草稿、更新字段）
- HIGH_RISK：高风险不可撤销（确认订单、取消订单）
- DANGEROUS：极高风险（退款、删除 - 未来扩展）
"""
from __future__ import annotations

import logging
from enum import Enum
from functools import wraps
from typing import Any, Callable

from app.core.permission import (
    PermissionDecision,
    PermissionRequest,
    PermissionResult,
    get_permission_engine,
)

logger = logging.getLogger(__name__)


class ToolPermission(str, Enum):
    """工具权限等级."""

    READ = "read"               # 只读
    WRITE = "write"             # 写入但可撤销
    HIGH_RISK = "high_risk"     # 高风险需 HITL
    DANGEROUS = "dangerous"     # 极高风险（未来）


# ============ 工具权限元数据 ============

TOOL_PERMISSIONS: dict[str, ToolPermission] = {
    # READ 类
    "search_hair_knowledge": ToolPermission.READ,
    "list_branches": ToolPermission.READ,
    "list_stylists": ToolPermission.READ,
    "recommend_services": ToolPermission.READ,

    # WRITE 类（可撤销）
    "create_draft_order": ToolPermission.WRITE,
    "update_order_fields": ToolPermission.WRITE,

    # HIGH_RISK 类（需 HITL）
    "confirm_order": ToolPermission.HIGH_RISK,
    "cancel_order": ToolPermission.HIGH_RISK,
}


def get_tool_permission(tool_name: str) -> ToolPermission:
    """获取工具的权限等级.

    未登记的工具默认按 HIGH_RISK 处理（保守策略，符合 JavaGuide 最小权限原则）.
    """
    return TOOL_PERMISSIONS.get(tool_name, ToolPermission.HIGH_RISK)


# ============ 装饰器 ============

def require_permission_decision(tool_name: str | None = None) -> Callable:
    """装饰器：在工具执行前先过权限判定.

    用法:
        @require_permission_decision("confirm_order")
        async def confirm_order(user_id: int, ...) -> str:
            ...

    行为 (与 PermissionEngine 三态对齐):
    1. ALLOWED → 正常执行被装饰函数
    2. ASKING → 内部 create_pending_ask, 返回 ask_id 字符串提示
       (前端可调 /api/permission/resolve 批准/拒绝)
    3. DENIED → 抛出 PermissionError

    Returns:
        被装饰函数的返回值 (str) 或 ASKING 时的提示字符串 (含 ask_id)

    Args:
        tool_name: 工具名（默认用函数名 __name__）
    """
    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 或 args 提取 user_id
            user_id = kwargs.get("user_id")
            if user_id is None and args:
                # 假设第一个 arg 是 user_id（按我们的约定）
                user_id = args[0]

            if user_id is None:
                logger.warning("require_permission_decision: no user_id for %s", name)
                # 没有 user_id 走默认流程
                return await func(*args, **kwargs)

            engine = get_permission_engine()
            request = PermissionRequest(
                user_id=int(user_id),
                tool_name=name,
                tool_args=kwargs,
            )
            result = engine.evaluate(request)

            if result.decision == PermissionDecision.DENIED:
                raise PermissionError(result.deny_message or "权限拒绝")

            if result.decision == PermissionDecision.ASKING:
                # 闭环 ASKING: 创建 ask_id 让前端可调 /api/permission/resolve
                # 返回字符串 (LLM 可见) 而非 dict, 这样工具结果仍是 str 类型
                ask_id = engine.create_pending_ask(request, result)
                return (
                    f"⚠️ [需要确认] {result.ask_message or result.reason or '此操作需要您确认'}。\n"
                    f"ask_id={ask_id}\n"
                    f"请确认后再次提交。"
                )

            # ALLOWED → 执行
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def check_tool_permission(user_id: int, tool_name: str, tool_args: dict) -> PermissionResult:
    """直接检查工具权限（不装饰）.

    Returns:
        PermissionResult
    """
    engine = get_permission_engine()
    request = PermissionRequest(
        user_id=user_id,
        tool_name=tool_name,
        tool_args=tool_args,
    )
    return engine.evaluate(request)


# ============ LangGraph 节点辅助 ============

async def safe_call_tool(
    tool_func: Callable,
    user_id: int,
    tool_name: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """LangGraph 节点调工具的安全包装.

    行为：
    - 权限 ALLOWED → 执行工具，返回 result
    - 权限 ASKING → 写 pending_ask_id 到 state，返回 ask_id
    - 权限 DENIED → 返回错误 dict
    - 工具异常 → 返回错误 dict

    Returns:
        {
            "ok": True, "result": ...,  # 成功
            "ok": False, "error": ...,  # 错误
            "needs_asking": True, "ask_id": ..., "reason": ...,  # 等待用户确认
        }
    """
    # 1. 权限检查
    perm = check_tool_permission(user_id, tool_name, kwargs)
    if perm.decision == PermissionDecision.DENIED:
        return {
            "ok": False,
            "error": perm.deny_message or "权限拒绝",
        }
    if perm.decision == PermissionDecision.ASKING:
        engine = get_permission_engine()
        request = PermissionRequest(user_id=user_id, tool_name=tool_name, tool_args=kwargs)
        ask_id = engine.create_pending_ask(request, perm)
        return {
            "needs_asking": True,
            "ask_id": ask_id,
            "reason": perm.reason,
            "ask_message": perm.ask_message,
        }

    # 2. 执行工具
    try:
        result = await tool_func(user_id=user_id, **kwargs)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("Tool %s failed: %s", tool_name, e)
        return {"ok": False, "error": str(e)}


__all__ = [
    "ToolPermission",
    "TOOL_PERMISSIONS",
    "get_tool_permission",
    "require_permission_decision",
    "check_tool_permission",
    "safe_call_tool",
]
