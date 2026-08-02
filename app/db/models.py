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
