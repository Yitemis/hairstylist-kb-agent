"""数据库自动迁移（Alembic + 启动时跑）。"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from app.db.session import engine, database_config

logger = logging.getLogger(__name__)

# Alembic 配置路径
ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def get_alembic_config() -> Config:
    """构造 Alembic Config。"""
    from pathlib import Path as _P
    cfg = Config(str(ALEMBIC_INI))
    # 强制用 SQLAlchemy URL（覆盖 alembic.ini 里的）
    cfg.set_main_option("sqlalchemy.url", database_config.resolved_url)
    # 强制设 script_location（alembic.ini 路径含冒号时无法解析）
    al = str((_P(__file__).parent.parent.parent / "alembic").resolve()).replace(chr(92), "/")
    cfg.set_main_option("script_location", al)
    return cfg


def get_current_revision() -> str | None:
    """获取当前数据库的迁移版本（alembic_version 表）。"""
    from sqlalchemy import create_engine
    sync_url = database_config.resolved_url.replace("+aiosqlite", "")
    sync_engine = create_engine(sync_url)
    try:
        with sync_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            return ctx.get_current_revision()
    finally:
        sync_engine.dispose()


def _get_head_revision_impl(cfg):  # helper for head
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()


def get_head_revision() -> str | None:
    """获取最新迁移版本。"""
    cfg = get_alembic_config()
    return _get_head_revision_impl(cfg)


async def run_migrations_on_startup() -> None:
    """启动时自动跑 alembic upgrade head。

    借鉴 12-factor app：进程启动 = 配置就绪。
    生产环境必须先迁移再服务，否则会读到旧 schema。
    """
    current = get_current_revision()
    head = get_head_revision()
    logger.info("DB migration: current=%s head=%s", current, head)
    if current == head:
        logger.info("DB schema is up to date")
        return
    if current is None:
        logger.info("No alembic_version table; running upgrade head (fresh DB)")
    else:
        logger.info("DB schema out of date: %s -> %s, running upgrade", current, head)
    # 同步跑 alembic（alembic 不支持 async）
    cfg = get_alembic_config()
    try:
        # 必须在子进程跑（避免与 async 引擎冲突）
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=str(ALEMBIC_INI.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.error("Alembic upgrade failed: %s", result.stderr)
            raise RuntimeError(f"DB migration failed: {result.stderr[:500]}")
        logger.info("Alembic upgrade head: %s", result.stdout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Alembic upgrade timeout (>60s)")
    except FileNotFoundError:
        # alembic 命令找不到，回退到 in-process
        logger.warning("alembic command not found, using in-process")
        command.upgrade(cfg, "head")


def is_migration_needed() -> bool:
    """健康检查：是否需要迁移。"""
    try:
        return get_current_revision() != get_head_revision()
    except Exception:
        return None
