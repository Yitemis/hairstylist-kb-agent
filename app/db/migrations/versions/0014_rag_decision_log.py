# -*- coding: utf-8 -*-
"""add rag_decision_log (Harness v2 §6.1)

Revision ID: 0014_rag_decision_log
Revises: 0013_tool_audit_log
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_rag_decision_log"
down_revision = "0013_tool_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """建 rag_decision_log 表 (一次 RAG 调用的完整决策日志)."""
    op.create_table(
        "rag_decision_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),

        # Phase 1: Intake
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("intake_route", sa.String(20), nullable=False),

        # Phase 2: Rewrite
        sa.Column("rewrite_strategies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rewrite_candidates", sa.JSON(), nullable=False, server_default="[]"),

        # Phase 3: Recall
        sa.Column("vector_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bm25_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recall_count", sa.Integer(), nullable=False, server_default="0"),

        # Phase 4: Rerank
        sa.Column("rerank_top_n", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rerank_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        # Phase 5: Gate
        sa.Column("gate_decision", sa.String(20), nullable=False, server_default="proceed"),
        sa.Column("gate_reason", sa.String(200), nullable=True),
        sa.Column("top1_score", sa.Float(), nullable=False, server_default="0.0"),

        # Phase 6: Compress
        sa.Column("context_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_tokens", sa.Integer(), nullable=False, server_default="0"),

        # Phase 7: Generate
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_latency_ms", sa.Integer(), nullable=False, server_default="0"),

        # Phase 8: Validate
        sa.Column("validator_passed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("validator_reason", sa.String(200), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),

        # Meta
        sa.Column("version_tag", sa.String(20), nullable=False, server_default="v1", index=True),
        sa.Column("phase_latencies", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # 复合索引: 按 tenant + created_at 查 (RePlayHook 用)
    op.create_index(
        "ix_rag_decision_log_tenant_created",
        "rag_decision_log",
        ["tenant_id", "created_at"],
    )
    # 按 gate_decision + created_at 查 (归因分析)
    op.create_index(
        "ix_rag_decision_log_gate_created",
        "rag_decision_log",
        ["gate_decision", "created_at"],
    )


def downgrade() -> None:
    """回滚."""
    op.drop_index("ix_rag_decision_log_gate_created", table_name="rag_decision_log")
    op.drop_index("ix_rag_decision_log_tenant_created", table_name="rag_decision_log")
    op.drop_table("rag_decision_log")
