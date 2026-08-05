"""add pending_actions table (HITL)

Revision ID: 0003_add_pending_actions
Revises: 0002_add_tsvector_index
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_pending_actions"
down_revision: Union[str, Sequence[str], None] = "0002_add_tsvector_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("action_type", sa.String(50), nullable=False, index=True),
        sa.Column("action_params", sa.JSON, default=dict, nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_pending_actions_user_status", "pending_actions", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_pending_actions_user_status", "pending_actions")
    op.drop_table("pending_actions")
