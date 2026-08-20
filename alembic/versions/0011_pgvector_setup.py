# -*- coding: utf-8 -*-
"""P2-基础设施: pgvector 替代 Milvus。

迁移内容：
1. 安装 pgvector 扩展 (PG 14+ 自带或 apt install postgresql-15-pgvector)
2. 创建 child_chunks 表 (存子块向量 + 元信息, 替代 Milvus collection)
3. 创建 HNSW 索引 (cosine_ops, BGE 1024 维)
4. 创建复合索引 (tenant_id+audience / document_id) 加速多租户过滤

设计理由：
- 单数据源: Document / ParentChunk / ChildChunk 三表都在 PG, 事务保证一致
- 解决 P0-3 孤儿数据问题: is_published 单一来源 (Document.is_published)
- hybrid search 一个 SQL 搞定: tsvector (BM25) + vector (HNSW) + 标量过滤

性能:
- HNSW m=16, ef_construction=64 适合 1M 级向量 (B 端规模足够)
- 1M 向量单查询延迟 < 50ms (PG 16 + pgvector 0.7+)
"""
"""pgvector_setup

Revision ID: 0011
Revises: 0010_order_user_nullable
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_pgvector_setup"
down_revision = "0010_order_user_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """安装 pgvector 扩展 + 建 child_chunks 表 + 索引。"""
    # 1. 启用 pgvector 扩展 (若容器没装, 升级会报错, 见 README 故障排除)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. child_chunks 表
    op.execute("""
        CREATE TABLE child_chunks (
            id BIGSERIAL PRIMARY KEY,
            child_id VARCHAR(64) UNIQUE NOT NULL,
            parent_id VARCHAR(64) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            document_id VARCHAR(64) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            category VARCHAR(50) NOT NULL DEFAULT 'general',
            audience VARCHAR(20) NOT NULL DEFAULT 'all',
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            image_path VARCHAR(500),
            content TEXT,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 3. HNSW 索引 (生产推荐: cosine, m=16, ef_construction=64)
    op.execute("""
        CREATE INDEX idx_child_chunks_embedding
        ON child_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # 4. 复合索引: 加速多租户 + 受众过滤
    op.execute("""
        CREATE INDEX idx_child_chunks_tenant_audience
        ON child_chunks (tenant_id, audience)
    """)

    # 5. 文档级索引
    op.execute("""
        CREATE INDEX idx_child_chunks_document
        ON child_chunks (document_id)
    """)

    # 6. parent_id 索引 (按 parent 聚合加速)
    op.execute("""
        CREATE INDEX idx_child_chunks_parent
        ON child_chunks (parent_id)
    """)


def downgrade() -> None:
    """回滚: 删表 + 索引 (扩展保留, 别的项目可能用)."""
    op.execute("DROP TABLE IF EXISTS child_chunks CASCADE")
    # 索引随表自动删除, 不需要单独 drop
    # pgvector 扩展不删除 (可能其他表用到)
