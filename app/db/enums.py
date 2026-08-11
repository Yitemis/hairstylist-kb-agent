# -*- coding: utf-8 -*-
"""业务状态枚举（单一数据源，杜绝散落字符串）。

借鉴 JavaGuide 状态机设计：
- Enum 定义合法状态
- Transition 定义合法转换
- 全项目用 OrderStatus.X.value，禁止写裸字符串
"""
from __future__ import annotations
from enum import Enum
from typing import Set


class OrderStatus(str, Enum):
    """订单状态（5 个，互斥）。"""
    DRAFT = "draft"          # 草稿（用户创建，未填全）
    PENDING = "pending"      # 待确认（用户提交，店家未处理）
    CONFIRMED = "confirmed"  # 已确认（店家接受预约）
    DONE = "done"            # 已完成
    CANCELLED = "cancelled"  # 已取消


# 合法状态转换
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.PENDING, OrderStatus.CANCELLED},
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.DONE, OrderStatus.CANCELLED},
    OrderStatus.DONE: set(),  # 终态
    OrderStatus.CANCELLED: set(),  # 终态
}


def can_transition(from_status: str, to_status: str) -> bool:
    """检查状态转换是否合法。"""
    try:
        f = OrderStatus(from_status)
        t = OrderStatus(to_status)
    except ValueError:
        return False
    return t in ORDER_STATUS_TRANSITIONS.get(f, set())


class OrderStatusLabels:
    """前端显示标签。"""
    LABELS = {
        OrderStatus.DRAFT: "草稿",
        OrderStatus.PENDING: "待确认",
        OrderStatus.CONFIRMED: "已确认",
        OrderStatus.DONE: "已完成",
        OrderStatus.CANCELLED: "已取消",
    }

    @classmethod
    def get(cls, status: str) -> str:
        try:
            return cls.LABELS[OrderStatus(status)]
        except (ValueError, KeyError):
            return status
