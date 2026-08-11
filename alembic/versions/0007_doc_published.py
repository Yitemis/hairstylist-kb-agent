"""add document published status

Revision ID: 0007_doc_published
Revises: 0006_idempotency_records
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_doc_published"
down_revision: Union[str, Sequence[str], None] = "0006_idempotency_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 加 published + published_at 字段
    op.add_column("documents", sa.Column("is_published", sa.Boolean, default=False, nullable=False, server_default="false"))
    op.add_column("documents", sa.Column("published_at", sa.DateTime, nullable=True))
    op.create_index("ix_documents_published", "documents", ["tenant_id", "is_published"])


def downgrade() -> None:
    op.drop_index("ix_documents_published", table_name="documents")
    op.drop_column("documents", "published_at")
    op.drop_column("documents", "is_published")
