# -*- coding: utf-8 -*-
"""HITL 权限三态引擎：借鉴 AgentScope 2.0 的 PermissionEngine。

核心概念：
- 每个工具调用在执行前先过权限判定
- 三种结果：
  - ALLOWED: 直接执行
  - ASKING: 需用户确认（危险操作），Agent 暂停等审批
  - DENIED: 拒绝执行（违规操作）
- 配合 PermissionRule（规则集）+ PermissionBehavior（默认行为）

场景：
- list_branches / list_stylists / list_services / create_draft_order / update_order_fields → ALLOWED（默认安全）
- confirm_order → ASKING（涉及最终金钱和时间承诺）
- recommend_services → ALLOWED
- cancel_order → ASKING（用户主动操作仍需确认）
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class PermissionDecision(str, Enum):
    """权限判定三态。"""
    ALLOWED = "allowed"
    ASKING = "asking"  # 需要用户确认
    DENIED = "denied"


@dataclass
class PermissionRequest:
    """权限请求。"""
    user_id: int
    tool_name: str
    tool_args: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionResult:
    """权限判定结果。"""
    decision: PermissionDecision
    reason: str = ""  # 为什么是 ALLOWED/ASKING/DENIED
    deny_message: str = ""  # DENIED 时给用户的错误提示
    ask_message: str = ""  # ASKING 时给用户的确认提示
    metadata: dict[str, Any] = field(default_factory=dict)


class PermissionRule(ABC):
    """权限规则基类。"""

    @abstractmethod
    def evaluate(self, request: PermissionRequest) -> PermissionResult | None:
        """评估请求，返回 None 表示不匹配（继续下一条规则）。"""
        ...


class AllowAllRule(PermissionRule):
    """默认规则：全部允许。"""

    def evaluate(self, request: PermissionRequest) -> PermissionResult:
        return PermissionResult(
            decision=PermissionDecision.ALLOWED,
            reason="默认允许",
        )


class ToolSpecificRule(PermissionRule):
    """针对特定工具的规则。"""

    def __init__(
        self,
        tool_rules: dict[str, PermissionDecision],
        reasons: dict[str, str] | None = None,
        messages: dict[str, str] | None = None,
    ) -> None:
        self.tool_rules = tool_rules
        self.reasons = reasons or {}
        self.messages = messages or {}

    def evaluate(self, request: PermissionRequest) -> PermissionResult | None:
        if request.tool_name not in self.tool_rules:
            return None
        decision = self.tool_rules[request.tool_name]
        return PermissionResult(
            decision=decision,
            reason=self.reasons.get(request.tool_name, ""),
            deny_message=self.messages.get(request.tool_name, "") if decision == PermissionDecision.DENIED else "",
            ask_message=self.messages.get(request.tool_name, "") if decision == PermissionDecision.ASKING else "",
        )


class ArgsBasedRule(PermissionRule):
    """基于参数的规则（如金额 > X 需确认）。"""

    def __init__(
        self,
        tool_name: str,
        predicate: Callable[[dict], bool],
        decision: PermissionDecision,
        reason: str = "",
        message: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.predicate = predicate
        self.decision = decision
        self.reason = reason
        self.message = message

    def evaluate(self, request: PermissionRequest) -> PermissionResult | None:
        if request.tool_name != self.tool_name:
            return None
        if not self.predicate(request.tool_args):
            return None
        return PermissionResult(
            decision=self.decision,
            reason=self.reason,
            ask_message=self.message,
            deny_message=self.message,
        )


class PermissionEngine:
    """权限引擎：按规则链判定。"""

    def __init__(self) -> None:
        self._rules: list[PermissionRule] = []
        self._pending_asks: dict[str, PermissionRequest] = {}  # ask_id -> request

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)
        logger.debug("注册权限规则: %s", rule.__class__.__name__)

    def evaluate(self, request: PermissionRequest) -> PermissionResult:
        """按规则链评估，返回第一个匹配的结果。"""
        for rule in self._rules:
            try:
                result = rule.evaluate(request)
                if result is not None:
                    logger.info(
                        "权限判定: %s %s -> %s (%s)",
                        request.tool_name, request.user_id, result.decision.value, result.reason,
                    )
                    return result
            except Exception as e:
                logger.warning("规则评估失败: %s", e)
        # 默认允许
        return PermissionResult(decision=PermissionDecision.ALLOWED, reason="无规则匹配")

    def create_pending_ask(self, request: PermissionRequest, result: PermissionResult) -> str:
        """记录 pending 询问，返回 ask_id（用户后续用此 ID 确认/拒绝）。"""
        import uuid
        ask_id = str(uuid.uuid4())[:8]
        self._pending_asks[ask_id] = (request, result)
        logger.info("创建 pending ask: %s for %s", ask_id, request.tool_name)
        return ask_id

    def resolve_ask(self, ask_id: str, approved: bool) -> tuple[PermissionRequest, PermissionResult] | None:
        """用户确认/拒绝。"""
        if ask_id not in self._pending_asks:
            return None
        request, original_result = self._pending_asks.pop(ask_id)
        if approved:
            return request, PermissionResult(decision=PermissionDecision.ALLOWED, reason="用户已批准")
        else:
            return request, PermissionResult(
                decision=PermissionDecision.DENIED,
                reason="用户已拒绝",
                deny_message="您已取消此操作",
            )


# 全局引擎 + 默认规则
_engine: PermissionEngine | None = None


def get_permission_engine() -> PermissionEngine:
    """获取全局权限引擎（懒加载，默认规则）。

    P0-3: 完整 RBAC 策略:
    - 查询类工具 (list_/get_) → ALLOWED (只读, 安全)
    - 写操作类工具 (update_/confirm_/cancel_) → ASKING (需用户确认)
    - 知识库/联网搜索 → ALLOWED (只读, 安全)
    """
    global _engine
    if _engine is None:
        _engine = PermissionEngine()
        # 1. 业务管理工具规则 (P0-3 新增)
        _engine.add_rule(ToolSpecificRule(
            tool_rules={
                # === 查询类: ALLOWED (只读) ===
                "list_orders": PermissionDecision.ALLOWED,
                "get_order_detail": PermissionDecision.ALLOWED,
                "list_branches": PermissionDecision.ALLOWED,
                "list_staffs": PermissionDecision.ALLOWED,
                "list_users": PermissionDecision.ALLOWED,
                "get_business_stats": PermissionDecision.ALLOWED,
                # === 写操作类: ASKING (需用户确认) ===
                "update_order_status": PermissionDecision.ASKING,
                "confirm_order": PermissionDecision.ASKING,
                "cancel_order": PermissionDecision.ASKING,
                # === 知识类: ALLOWED (只读) ===
                "search_hair_knowledge": PermissionDecision.ALLOWED,
                "web_search": PermissionDecision.ALLOWED,
                # === Booking 工具 (C 端预约) ===
                "create_draft_order": PermissionDecision.ALLOWED,
                "update_order_fields": PermissionDecision.ALLOWED,
                "list_stylists": PermissionDecision.ALLOWED,
                "recommend_services": PermissionDecision.ALLOWED,
            },
            reasons={
                "update_order_status": "修改订单状态属于写操作, 需用户确认",
                "confirm_order": "确认订单涉及金钱和时间承诺, 需用户确认",
                "cancel_order": "取消订单不可逆, 需用户确认",
            },
            messages={
                "update_order_status": "您即将修改订单状态, 此操作会立即生效. 请确认.",
                "confirm_order": "您即将确认这笔预约, 请确认信息无误.",
                "cancel_order": "您即将取消此预约, 取消后不可恢复.",
            },
        ))
        # 2. 默认: 其他工具 ALLOWED
        _engine.add_rule(AllowAllRule())
    return _engine
