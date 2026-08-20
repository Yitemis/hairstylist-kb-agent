# -*- coding: utf-8 -*-
"""P0: 添加文档级 permission_tag 字段.

借鉴九阳 POC §5: 4 步实施法 (Step 1: 模型 -> 2: migration -> 3: 写入 -> 4: 过滤).
"""
"""add_permission_tag_to_documents

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_add_permission_tag"
down_revision = "0008_drop_state_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加 permission_tag 字段 (default='public' 兼容旧数据)."""
    op.add_column(
        "documents",
        sa.Column("permission_tag", sa.String(20), nullable=False, server_default="public"),
    )
    op.create_index("ix_documents_permission_tag", "documents", ["permission_tag"])


def downgrade() -> None:
    op.drop_index("ix_documents_permission_tag", table_name="documents")
    op.drop_column("documents", "permission_tag")
