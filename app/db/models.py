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
    # B 端电话预约场景: 用户尚未注册 C 端账号, 允许 NULL (P1 + alembic 0010)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
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
    # P0-3: 会话 ID (区分多轮对话, SSE 持久化用)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 可选：关联到某个订单（如果是预约流程中产生的对话）
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    # 模式：booking / knowledge / fallback
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ToolAuditLog(Base):
    """工具调用审计日志 (P0-3: B 端管理 agent).

    记录每次 agent 调工具的:
    - 谁 (actor_id + actor_type)
    - 干了什么 (tool_name + args + result)
    - 权限判定 (allowed/asking/denied)
    - 上下文 (intent, session, user_message)
    - 何时 (created_at)

    用于: 安全审计 / 异常检测 / 合规 / 用户行为分析
    """
    __tablename__ = "tool_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # staff / user / admin
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    tool_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # 截断 1000
    permission: Mapped[str] = mapped_column(String(20), nullable=False)  # allowed/asking/denied
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # 截断 500
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


class ChatSession(Base, TimestampMixin):
    """对话会话元数据（状态由 AgentStateStore / Redis 统一管理, P0-5）。

    P0-5 修复: 删除 state_json 字段, 状态统一存 AgentStateStore (Redis),
    避免双数据源不一致。前端 list_sessions 只读 state_store。

    保留字段:
    - session_id: 会话唯一 ID
    - user_id: 用户 ID
    - title: 对话标题（首条消息摘要）
    - pending_order_id: 进行中的订单 ID（草稿）
    - interrupted: 是否被打断
    - last_iter: 最后一次迭代次数"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 对话标题（首条消息摘要）
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




class IdempotencyRecord(Base, TimestampMixin):
    """幂等记录：避免重复创建（订单 / 支付 等高风险操作）。

    借鉴 JavaGuide idempotency.md + Stripe API 设计：
    - 客户端传 Idempotency-Key: <uuid>
    - 服务端：第一次调实际执行，后续直接返回缓存
    - 4 要素：唯一 key + 状态 + 持久化 + 过期
    - TTL 24h (防误操作 + 兼顾性能)
    """

    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # body hash 防 key 复用但 body 不同
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


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
    """图片块元信息（vector 存 pgvector child_chunks 表，元信息存业务库）。

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
# - 向量库 (pgvector child_chunks 表) 只存子块（vector + parent_id 引用 + 元信息）
# - 检索：向量召回子块 → 按 parent_id 批量查业务库拿父块 → Rerank
# 优势：父块不重复存在向量库 payload 中，节省空间 + 加快向量检索


class Document(Base, TimestampMixin):
    """知识库文档元信息.

    字段对应 MinerU 解析后的元数据 + 业务元信息 + Harness v2 §7.1 知识更新元数据.
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
    # 软删除 (deleted_at 兼容老代码, is_deleted 新加, 二者等价)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 版本号（incremental update 用）
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    parent_chunks: Mapped[list["ParentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    # 受众隔离：user=C 端用户, staff=商家员工, all=所有人
    audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False, index=True)
    # 发布状态：True=已发布，RAG 检索可命中
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # P0 权限标签 (借鉴九阳 POC §5: 4 步实施法)
    # public: C 端用户可访问 / internal: 员工可访问 / confidential: 仅管理员
    permission_tag: Mapped[str] = mapped_column(
        String(20), default="public", nullable=False, index=True,
    )

    # ============== Harness v2 §7.1: 知识更新元数据 ==============
    # 内容指纹 (SHA-256, 64 字符) - 去重用
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 版本号 (递增, 增量更新追踪)
    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 软删除标记 (和 deleted_at 等价, KnowledgeUpdater 写这个)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # 注: updated_at 已在 TimestampMixin 中 (server_default=now()), 不重复
    # 分块策略
    chunk_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Embedding 模型信息 (IndexAlias 切换用)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)



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

    # Harness v2 §7.1: ParentChunk 元数据
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)


# ============================================================
# P2-基础设施: pgvector 子块表 (替代 Milvus collection)
# ============================================================
# 借鉴 WeKnora + ekbs 设计:
# - 子块存向量, 父块存业务库 (parent_chunks)
# - 子块额外存 content 字段, 方便 debug 和 score >= 1 的 hit 直接回显
# - 业务唯一 ID (child_id) 用 UUID 字符串, 对外暴露不用 BIGSERIAL
#
# 设计理由:
# - 三表 (Document/ParentChunk/ChildChunk) 在同一 DB, 事务保证一致
# - is_published JOIN Document 表查, 解决 P0-3 双源不一致
# - hybrid search 一个 SQL 搞定 (tsvector + vector + 标量 filter)

try:
    from pgvector.sqlalchemy import Vector
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "pgvector 未安装. 请运行: pip install pgvector>=0.3.0"
    ) from e


class ChildChunk(Base):
    """子块（向量检索单位）。

    Attributes:
        child_id: 业务唯一 ID (UUID, 对外暴露)
        parent_id: 关联 ParentChunk.parent_id
        tenant_id: 多租户隔离
        document_id: 关联 Document.document_id
        filename: 冗余存储, 检索时不用 JOIN 就能拿到
        category: 知识库组别 (perming/cutting/coloring/care/general/image)
        audience: 受众 (user/staff/all)
        is_published: 冗余字段, JOIN Document 表时会再校验 (单源真相)
        image_path: 图片专用 (image_indexer 写入)
        content: 子块文本 (便于 debug / 直接回显 / 不用回查 parent)
        embedding: 1024 维向量 (BGE-large-zh-v1.5)
    """

    __tablename__ = "child_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    parent_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False, index=True)
    audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False, index=True)
    # 冗余字段: 单一来源仍是 Document.is_published (JOIN 时校验)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # 图片专用 (image_indexer 写入)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 子块文本 (新设计: 不回查 parent 也能显示内容, 简化代码)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 1024 维向量 (BGE-large-zh-v1.5)
    embedding = mapped_column(Vector(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    # Harness v2 §7.1: Embedding 模型信息 + 索引别名 (蓝绿切换)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    index_alias: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, default="default",
    )


class RagDecisionLog(Base):
    """RAG 决策日志 (Harness v2 §6.1): 一次 RAG 调用的完整决策日志.

    借鉴 JavaGuide observability + Milvus audit 设计:
    - trace_id 串联整条调用链
    - 8 个阶段全部落库, 供 ReplayHook 回放 + A/B + 归因分析
    - 失败也写 (error 字段), 便于故障排查
    """
    __tablename__ = "rag_decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )

    # Phase 1: Intake
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    intake_route: Mapped[str] = mapped_column(String(20), nullable=False)

    # Phase 2: Rewrite
    rewrite_strategies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rewrite_candidates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Phase 3: Recall
    vector_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bm25_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recall_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Phase 4: Rerank
    rerank_top_n: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rerank_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Phase 5: Gate
    gate_decision: Mapped[str] = mapped_column(String(20), default="proceed", nullable=False)
    gate_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    top1_score: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Phase 6: Compress
    context_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Phase 7: Generate
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    answer_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Phase 8: Validate
    validator_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validator_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Meta
    version_tag: Mapped[str] = mapped_column(String(20), default="v1", nullable=False, index=True)
    phase_latencies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
