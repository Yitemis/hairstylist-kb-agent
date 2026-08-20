# -*- coding: utf-8 -*-
"""P1: orders.user_id 改为可空 (B 端电话预约场景不需要 C 端用户).

B 端商家手工下单时, 用户尚未注册 C 端账号, 所以 user_id 应允许为 NULL。
当 C 端用户后续注册时, 可通过 customer_phone 反向关联补全 user_id。
"""
"""order_user_nullable

Revision ID: 0010
Revises: 0009_add_permission_tag
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_order_user_nullable"
down_revision = "0009_add_permission_tag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """orders.user_id 允许 NULL。"""
    op.alter_column("orders", "user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """回滚: 恢复 NOT NULL (注: 如果有 NULL 数据会失败, 需要先清理)."""
    op.execute("UPDATE orders SET user_id = (SELECT id FROM users LIMIT 1) WHERE user_id IS NULL")
    op.alter_column("orders", "user_id", existing_type=sa.Integer(), nullable=False)
