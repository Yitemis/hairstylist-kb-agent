"""add idempotency_records table (P0-4, 借鉴 JavaGuide idempotency)

Revision ID: 0006_idempotency_records
Revises: 0005_add_audience
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_idempotency_records"
down_revision: Union[str, Sequence[str], None] = "0005_add_audience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_idempotency_records_user_action", "idempotency_records", ["user_id", "action"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_user_action", "idempotency_records")
    op.drop_table("idempotency_records")
