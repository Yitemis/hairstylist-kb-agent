"""base schema (current state)

Revision ID: 0001_base_schema
Revises:
Create Date: 2026-08-04

说明：
- 标记当前 schema 状态为基线
- 后续 schema 变更会生成新的 migration 文件
- 启动时自动跑 `alembic upgrade head` 应用所有未应用的 migration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "0001_base_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """标记当前 schema 为基线。"""
    # 之前用 create_all 创建的表（不再重复创建）
    # 后续 schema 变更在新 migration 文件里写
    pass


def downgrade() -> None:
    """回滚基线（无操作）。"""
    pass
