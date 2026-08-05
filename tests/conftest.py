"""测试配置：所有测试前自动初始化 DB（兼容 PG + SQLite）。

关键：
- pytest-asyncio 用 session-scoped event_loop fixture
- asyncpg 连接绑定到 fixture 的 loop（避免 "different loop" 错）
- init_db 在 loop 内创建连接池
- 每个测试清空 Milvus + PG（避免测试间污染）
"""
import asyncio
import sys

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    if sys.platform == "win32":
        asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="session")
def init_db_session(event_loop):
    async def _init():
        from app.db.session import init_db
        from app.db import models
        await init_db()
    event_loop.run_until_complete(_init())
    yield


@pytest.fixture(autouse=True)
def _milvus_cleanup(request):
    """每个测试前清空 Milvus，但 keep_milvus marker 可跳过。"""
    has_marker = request.node.get_closest_marker("keep_milvus") is not None
    if has_marker:
        print("[CONFTEST] keep_milvus detected, skip drop")
        yield
        return
    print("[CONFTEST] dropping Milvus collections")
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(uri="http://localhost:19530")
        for col in client.list_collections():
            try:
                client.drop_collection(col)
            except Exception:
                pass
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True, scope="session")
def seed_business_data(event_loop):
    async def _seed():
        from app.db.session import async_session_maker
        from app.db.models import Branch, Service, Stylist
        async with async_session_maker() as s:
            from sqlalchemy import select
            existing = (await s.execute(select(Branch))).first()
            if existing:
                return
            branch = Branch(
                name="总店", address="北京朝阳区", phone="13800000000",
                description="测试分店", latitude=39.9, longitude=116.4,
                max_daily_appointments=20, is_active=True,
            )
            s.add(branch)
            await s.flush()
            service = Service(
                name="基础剪发", category="剪发", description="标准剪发",
                duration_minutes=30, price=50.0, is_active=True,
            )
            s.add(service)
            await s.flush()
            stylist = Stylist(
                branch_id=branch.id, name="张三",
                specialties='["剪发", "染发"]', is_active=True,
            )
            s.add(stylist)
            await s.commit()
    try:
        event_loop.run_until_complete(_seed())
    except Exception as e:
        print(f"Seed business data failed: {e}")
    yield
