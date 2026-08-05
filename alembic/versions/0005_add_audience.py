"""add audience column for role-based KB isolation

Revision ID: 0005_add_audience
Revises: 0004_add_image_chunks
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_audience"
down_revision: Union[str, Sequence[str], None] = "0004_add_image_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("audience", sa.String(20), server_default="all", nullable=False))
    op.create_index("ix_documents_audience", "documents", ["audience"])
    op.add_column("image_chunks", sa.Column("audience", sa.String(20), server_default="all", nullable=False))
    op.create_index("ix_image_chunks_audience", "image_chunks", ["audience"])


def downgrade() -> None:
    op.drop_index("ix_image_chunks_audience", "image_chunks")
    op.drop_column("image_chunks", "audience")
    op.drop_index("ix_documents_audience", "documents")
    op.drop_column("documents", "audience")
