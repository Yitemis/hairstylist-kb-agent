# -*- coding: utf-8 -*-
"""ORM 模型：用户 / 店家 / 发型师 / 服务项目 / 订单。

对齐 docs/TEMP_数据库设计.md。字段命名与前端接口契约保持一致。
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    """统一创建/更新时间戳。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Base, TimestampMixin):
    """C 端用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Staff(Base, TimestampMixin):
    """B 端店家/员工。"""

    __tablename__ = "staffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="worker", nullable=False)


class Branch(Base, TimestampMixin):
    """分店（多分店支持）。"""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    max_daily_appointments: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 不限制
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stylists: Mapped[list["Stylist"]] = relationship(back_populates="branch")
    orders: Mapped[list["Order"]] = relationship(back_populates="branch")


class Stylist(Base, TimestampMixin):
    """发型师。每个发型师属于一家分店。"""

    __tablename__ = "stylists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    specialties: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_daily_hours: Mapped[int] = mapped_column(Integer, default=8, nullable=False)  # 每日最大工作小时
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    branch: Mapped["Branch | None"] = relationship(back_populates="stylists")
    orders: Mapped[list["Order"]] = relationship(back_populates="stylist")


class Service(Base, TimestampMixin):
    """服务项目。"""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # 烫发/染发/护理/剪发/造型
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Order(Base, TimestampMixin):
    """预约订单（核心）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    stylist_id: Mapped[int | None] = mapped_column(ForeignKey("stylists.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)

    service_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    appointment_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    appointment_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    conversation_history: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    user: Mapped["User"] = relationship(back_populates="orders")
    branch: Mapped["Branch | None"] = relationship(back_populates="orders")
    stylist: Mapped["Stylist | None"] = relationship(back_populates="orders")


class ChatMessage(Base, TimestampMixin):
    """对话消息（用于 Agent 记忆）。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' | 'ai' | 'system'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 可选：关联到某个订单（如果是预约流程中产生的对话）
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    # 模式：booking / knowledge / fallback
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ChatSession(Base, TimestampMixin):
    """对话会话（用于状态持久化 + 跨服务器恢复）。

    借鉴 AgentScope 2.0 的 AgentState 设计：
    - session_id: 会话唯一 ID（用户可自定义 / 自动生成）
    - user_id: 用户 ID
    - state_json: 完整状态快照（dict 序列化）
    - 状态字段：
        - context: 消息列表（也可在 chat_messages 表查）
        - pending_orders: 进行中的订单 ID 列表（草稿）
        - plan_mode: 是否在 Plan 模式
        - interrupted: 是否被打断
        - last_iter: 最后一次迭代次数
        - extra: 其他业务自定义字段
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 对话标题（首条消息摘要）
    state_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 完整状态 JSON
    pending_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_iter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserProfile(Base, TimestampMixin):
    """用户长期记忆：跨会话保存的事实。

    借鉴 AgentScope 2.0 的"应用层长期记忆"模式：
    - 框架负责"本轮对话状态"（AgentState）
    - 应用负责"跨会话偏好"（UserProfile）

    例子：
        - ("preferred_stylist", "张托尼")
        - ("allergic_to", "阿摩尼亚染膏")
        - ("address", "上海徐汇区...")
        - ("birthday", "1990-01-01")
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    fact_key: Mapped[str] = mapped_column(String(50), nullable=False)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源：对话 ID（用于追溯 + 重复时更新）
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_messages.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(default=1.0, nullable=False)  # 0~1，LLM 给的置信度




class PendingAction(Base, TimestampMixin):
    """HITL 待确认 action。

    借鉴 OAuth 2.0 一次性授权码模式：
    - AI 想执行高风险操作 → 创建 PendingAction（生成 token 给前端）
    - 前端显示 '请确认' 卡片
    - 用户确认 → 带 token 回来 → 执行
    - Token 一次性 + 5 分钟过期（防 CSRF / 误操作）
    """

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)  # SHA-256
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# Index: 快速查 (user_id, status, expires_at)


class ImageChunk(Base, TimestampMixin):
    """图片块元信息（vector 存 Milvus，元信息存业务库）。

    借鉴 ekbs 设计：
    - 父子结构：图片关联到父块（同一章节/页面）
    - 多模态 embedding：图片转向量
    - 来源追溯：page / bbox / image_path
    """
    __tablename__ = "image_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    parent_chunk_id: Mapped[str] = mapped_column(String(64), index=True, nullable=True)  # 关联父块
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(20), default="image/jpeg", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="image", index=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


# ============================================================
# RAG 文档与父子分块模型
# ============================================================
# 借鉴 ekbs (LONG_TERM_MEMORY_EKBS_AI_SERVICE.md) 的设计：
# - Document: 文档元信息（不存内容，只存元数据）
# - ParentChunk: 父块全文（存业务库，可按 parent_id 查询）
# - 向量库 (Milvus) 只存子块（vector + parent_id 引用 + 元信息）
# - 检索：向量召回子块 → 按 parent_id 批量查业务库拿父块 → Rerank
# 优势：父块不重复存在向量库 payload 中，节省空间 + 加快向量检索


class Document(Base, TimestampMixin):
    pass  # placeholder
    """知识库文档元信息。

    字段对应 MinerU 解析后的元数据 + 业务元信息。
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 业务唯一 ID（前端用，UUID）
    document_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # 多租户隔离
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # 文件信息
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), default="pdf", nullable=False)
    # MinerU 解析状态
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mineru_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending / parsing / parsed / indexed / failed
    # 业务字段
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    # 软删除
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 版本号（incremental update 用）
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    parent_chunks: Mapped[list["ParentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    # 受众隔离（借鉴 RBAC）：user=C 端用户, staff=商家员工, all=所有人
    audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False, index=True)



class ParentChunk(Base, TimestampMixin):
    """父块（完整上下文）。

    借鉴 ekbs 设计：父块只存业务库，不存向量库。
    子块向量库只存 parent_id 引用 → 检索时批量查父块。
    """

    __tablename__ = "parent_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 业务唯一 ID（前端用，UUID，对应子块 parent_id）
    parent_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # 多租户隔离
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # 文档外键
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.document_id"), index=True, nullable=False
    )
    # 父块全文（最大 ~2000 token）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # token 数量（用于上下文管理）
    token_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 顺序（在文档中的位置，用于排序）
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 元信息（JSON 字符串）
    chunk_meta: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="parent_chunks")
