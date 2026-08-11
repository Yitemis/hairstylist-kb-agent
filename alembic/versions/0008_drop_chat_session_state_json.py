"""drop chat_sessions.state_json (P0-5)

state_json 字段已被 AgentStateStore (Redis) 取代, 写路径不再用, 读路径
已迁移到 list_session_ids()。这里彻底删除字段以消除双数据源。

Revision ID: 0008_drop_state_json
Revises: 0007_doc_published
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_drop_state_json"
down_revision: Union[str, Sequence[str], None] = "0007_doc_published"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P0-5: 删除 chat_sessions.state_json 字段
    # 单数据源: 状态统一存 AgentStateStore (Redis)
    op.drop_column("chat_sessions", "state_json")


def downgrade() -> None:
    # 回滚: 加回字段
    op.add_column("chat_sessions", sa.Column("state_json", sa.Text, nullable=True))
