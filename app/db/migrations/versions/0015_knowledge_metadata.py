# -*- coding: utf-8 -*-
"""add knowledge metadata (Harness v2 §7.1)

为 documents / parent_chunks / child_chunks 表补:
  - content_hash: SHA-256, 去重用
  - version_id: 文档版本号, 增量更新用
  - is_deleted: 软删除标记
  - embedding_model / embedding_model_version / embedding_dimension
  - chunk_strategy / chunk_size / chunk_overlap
  - updated_at: 更新时间戳 (增量更新用)

借鉴 JavaGuide rag-knowledge-update.md + Milvus Alias 设计.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_knowledge_metadata"
down_revision = "0014_rag_decision_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1. documents 表: 内容指纹 + 版本 + 软删
    # ============================================================
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(64), nullable=True, index=True),
    )
    op.add_column(
        "documents",
        sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "documents",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
    )
    # 注: updated_at 已在 TimestampMixin 创建 (documents.created_at/updated_at),
    # 不重复 add_column
    op.add_column(
        "documents",
        sa.Column("chunk_strategy", sa.String(50), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("chunk_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("chunk_overlap", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("embedding_model_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
    )

    # 复合索引: tenant + content_hash (去重查询)
    op.create_index(
        "ix_documents_tenant_content_hash",
        "documents",
        ["tenant_id", "content_hash"],
    )

    # ============================================================
    # 2. parent_chunks 表: embedding 模型信息 + 软删
    # ============================================================
    op.add_column(
        "parent_chunks",
        sa.Column("content_hash", sa.String(64), nullable=True, index=True),
    )
    op.add_column(
        "parent_chunks",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.add_column(
        "parent_chunks",
        sa.Column("embedding_model_version", sa.String(50), nullable=True),
    )

    # ============================================================
    # 3. child_chunks 表: embedding 模型信息 (用于 IndexAlias 切换)
    # ============================================================
    op.add_column(
        "child_chunks",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.add_column(
        "child_chunks",
        sa.Column("embedding_model_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "child_chunks",
        sa.Column("index_alias", sa.String(50), nullable=True, server_default="default"),
    )
    op.create_index(
        "ix_child_chunks_index_alias",
        "child_chunks",
        ["index_alias"],
    )


def downgrade() -> None:
    # child_chunks
    op.drop_index("ix_child_chunks_index_alias", table_name="child_chunks")
    op.drop_column("child_chunks", "index_alias")
    op.drop_column("child_chunks", "embedding_model_version")
    op.drop_column("child_chunks", "embedding_model")
    # parent_chunks
    op.drop_column("parent_chunks", "embedding_model_version")
    op.drop_column("parent_chunks", "embedding_model")
    op.drop_column("parent_chunks", "content_hash")
    # documents
    op.drop_index("ix_documents_tenant_content_hash", table_name="documents")
    op.drop_column("documents", "embedding_dimension")
    op.drop_column("documents", "embedding_model_version")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "chunk_overlap")
    op.drop_column("documents", "chunk_size")
    op.drop_column("documents", "chunk_strategy")
    # updated_at 不需要 drop (没在 upgrade 加)
    op.drop_column("documents", "is_deleted")
    op.drop_column("documents", "version_id")
    op.drop_column("documents", "content_hash")
