"""add tsvector column for full-text search

Revision ID: 0002_add_tsvector_index
Revises: 0001_base_schema
Create Date: 2026-08-04

说明：
- 给 documents / parent_chunks 加 content_tsv 列（PG TSVECTOR）
- 建 GIN 索引（毫秒级全文搜索）
- 中文分词：客户端用 jieba，存 tsvector 时用 'public.chinese_zh' 配置（PG zhparser 扩展）或 fallback 到 'simple'
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "0002_add_tsvector_index"
down_revision: Union[str, Sequence[str], None] = "0001_base_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加 tsvector 列 + GIN 索引。"""
    # parent_chunks: 存父块全文的 tsvector
    op.execute("""
        ALTER TABLE parent_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_parent_chunks_tsv
        ON parent_chunks USING GIN (content_tsv)
    """)
    # documents: 存文件名的 tsvector（轻量元信息）
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS filename_tsv tsvector
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_filename_tsv
        ON documents USING GIN (filename_tsv)
    """)


def downgrade() -> None:
    """回滚。"""
    op.execute("DROP INDEX IF EXISTS idx_documents_filename_tsv")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS filename_tsv")
    op.execute("DROP INDEX IF EXISTS idx_parent_chunks_tsv")
    op.execute("ALTER TABLE parent_chunks DROP COLUMN IF EXISTS content_tsv")
