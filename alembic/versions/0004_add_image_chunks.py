"""add image_chunks table (VLM 图片)

Revision ID: 0004_add_image_chunks
Revises: 0003_add_pending_actions
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_image_chunks"
down_revision: Union[str, Sequence[str], None] = "0003_add_pending_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("image_id", sa.String(64), unique=True, index=True, nullable=False),
        sa.Column("tenant_id", sa.String(50), index=True, nullable=False),
        sa.Column("document_id", sa.String(64), index=True, nullable=False),
        sa.Column("parent_chunk_id", sa.String(64), index=True, nullable=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(20), default="image/jpeg"),
        sa.Column("category", sa.String(50), default="image", index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("image_chunks")
