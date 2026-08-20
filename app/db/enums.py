# -*- coding: utf-8 -*-
"""业务状态枚举（单一数据源，杜绝散落字符串）.

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
    DRAFT = "draft"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DONE = "done"
    CANCELLED = "cancelled"


ORDER_STATUS_TRANSITIONS: dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.PENDING, OrderStatus.CANCELLED},
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.DONE, OrderStatus.CANCELLED},
    OrderStatus.DONE: set(),
    OrderStatus.CANCELLED: set(),
}


# ==================================================================
# 文档状态机 (P0-3: 借鉴 OrderStatus 模式统一管理)
# ==================================================================
class DocumentStatus(str, Enum):
    """文档解析状态机 (5 个状态).

    状态流转 (借鉴 JavaGuide 状态机):
      pending  → parsing       (用户点「开始学习」)
      parsing  → indexed       (解析成功, chunks 已入 pgvector)
      parsing  → failed        (解析报错)
      failed   → parsing       (用户重新点「开始学习」)
      indexed  → parsing       (用户强制重新解析)

    终态: indexed / failed (但 failed 可重新进入 parsing)
    """
    PENDING = "pending"      # 已上传, 未解析
    PARSING = "parsing"      # 正在解析
    PARSED = "parsed"        # 解析完成 (中间态, 暂未使用, 保留扩展位)
    INDEXED = "indexed"      # 已索引 (chunks 入 pgvector 完成, 可发布)
    FAILED = "failed"        # 解析失败


DOCUMENT_STATUS_TRANSITIONS: dict[DocumentStatus, Set[DocumentStatus]] = {
    DocumentStatus.PENDING: {DocumentStatus.PARSING, DocumentStatus.FAILED},  # P0-3: 加 FAILED (文件找不到等情况)
    DocumentStatus.PARSING: {DocumentStatus.INDEXED, DocumentStatus.FAILED, DocumentStatus.PENDING},  # P0-3: 加 PENDING (救场: 卡住时强制重置)
    DocumentStatus.PARSED: {DocumentStatus.INDEXED, DocumentStatus.FAILED},
    DocumentStatus.INDEXED: {DocumentStatus.PARSING},  # 允许重新解析
    DocumentStatus.FAILED: {DocumentStatus.PARSING, DocumentStatus.PENDING},  # 失败可重试, 也可救场重置
}


def can_transition_doc(from_status: str, to_status: str) -> bool:
    """检查文档状态流转是否合法."""
    try:
        f = DocumentStatus(from_status)
        t = DocumentStatus(to_status)
    except ValueError:
        return False
    return t in DOCUMENT_STATUS_TRANSITIONS.get(f, set())


def can_transition(from_status: str, to_status: str) -> bool:
    try:
        f = OrderStatus(from_status)
        t = OrderStatus(to_status)
    except ValueError:
        return False
    return t in ORDER_STATUS_TRANSITIONS.get(f, set())


class OrderStatusLabels:
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


# ============================================================
# P0: 文档级权限标签 (借鉴九阳 POC §5: 4 步实施法)
# ============================================================

class PermissionTag(str, Enum):
    """文档级权限标签 (3 维: 公开 / 内部 / 机密).

    借鉴九阳 POC 企业文档权限分级:
    - PUBLIC: C 端用户可访问 (产品科普)
    - INTERNAL: 员工可访问 (操作手册)
    - CONFIDENTIAL: 仅管理员可访问 (商业机密)
    """
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


# 用户角色 -> 可访问的权限标签
ROLE_PERMISSION_MATRIX: dict[str, Set[PermissionTag]] = {
    "user": {PermissionTag.PUBLIC},                           # C 端用户
    "staff": {PermissionTag.PUBLIC, PermissionTag.INTERNAL},  # 员工
    "admin": {PermissionTag.PUBLIC, PermissionTag.INTERNAL, PermissionTag.CONFIDENTIAL},  # 管理员
}


def can_access(role: str, permission_tag: str) -> bool:
    """检查某角色是否能访问某权限的文档.

    Args:
        role: 用户角色 (user/staff/admin)
        permission_tag: 文档权限 (public/internal/confidential)

    Returns:
        True if 可访问, False otherwise
    """
    try:
        tag = PermissionTag(permission_tag)
    except ValueError:
        # 未知权限标签, 保守处理: 拒绝
        return False
    allowed = ROLE_PERMISSION_MATRIX.get(role, set())
    return tag in allowed


def filter_by_role(
    documents: list,
    role: str,
    tag_field: str = "permission_tag",
) -> list:
    """按用户角色过滤文档列表 (移除无权访问的).

    Args:
        documents: 文档列表 (dict 或 dataclass)
        role: 用户角色
        tag_field: 权限字段名

    Returns:
        过滤后的文档列表
    """
    out = []
    for doc in documents:
        if isinstance(doc, dict):
            tag = doc.get(tag_field, "public")
        else:
            tag = getattr(doc, tag_field, "public")
        if can_access(role, tag):
            out.append(doc)
    return out
