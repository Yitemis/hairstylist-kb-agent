# -*- coding: utf-8 -*-
"""P0-3: chat_messages 加 session_id 字段 (让 SSE 流式能按会话存储历史)."""
"""chat_session_id

Revision ID: 0011
Revises: 0011_pgvector_setup
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_chat_session_id"
down_revision = "0011_pgvector_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("session_id", sa.String(64), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "session_id")
