# -*- coding: utf-8 -*-
"""P0-3: 加 tool_audit_log 表 (B 端管理 agent 工具调用审计)."""
"""tool_audit_log

Revision ID: 0013
Revises: 0012_chat_session_id
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_tool_audit_log"
down_revision = "0012_chat_session_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        # 谁 (P0-3: B 端用 staff.id, C 端用 user.id, 也可能是 admin 内部账号)
        sa.Column("actor_id", sa.Integer, nullable=False, index=True),
        sa.Column("actor_type", sa.String(20), nullable=False),  # 'staff' | 'user' | 'admin'
        # 干了什么
        sa.Column("tool_name", sa.String(64), nullable=False, index=True),
        sa.Column("tool_args", sa.Text, nullable=True),  # JSON 字符串
        sa.Column("tool_result", sa.Text, nullable=True),  # 截断 1000 字
        sa.Column("permission", sa.String(20), nullable=False),  # 'allowed' | 'asking' | 'denied'
        # 上下文
        sa.Column("intent", sa.String(20), nullable=True),  # 'knowledge' | 'booking' | 'management'
        sa.Column("session_id", sa.String(64), nullable=True, index=True),
        sa.Column("user_message", sa.Text, nullable=True),  # 原始用户消息 (截断 500)
        # IP/UA (可选, 安全审计)
        sa.Column("ip_address", sa.String(64), nullable=True),
        # 时间
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()"), index=True),
    )
    op.create_index("ix_audit_actor_time", "tool_audit_log", ["actor_id", "created_at"])
    op.create_index("ix_audit_tool_time", "tool_audit_log", ["tool_name", "created_at"])


def downgrade() -> None:
    op.drop_table("tool_audit_log")
