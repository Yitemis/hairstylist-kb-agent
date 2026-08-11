# -*- coding: utf-8 -*-
"""Redis state store 集成测试 (P0-5)。"""
import os
import pytest
import pytest_asyncio

os.environ.setdefault("AGENT_STATE_BACKEND", "redis")


@pytest.mark.asyncio
async def test_redis_state_store_save_and_get():
    """真实 Redis 存取。"""
    from app.core.agent_state_store import get_state_store, RedisAgentStateStore
    store = get_state_store()
    if not isinstance(store, RedisAgentStateStore):
        pytest.skip("Redis not available, skipped")
    store.save("u1", "s1", "key1", {"foo": "bar", "n": 42})
    got = store.get("u1", "s1", "key1")
    assert got == {"foo": "bar", "n": 42}
    store.delete("u1", "s1")
    assert store.get("u1", "s1", "key1") is None


@pytest.mark.asyncio
async def test_redis_state_store_list_sessions():
    """session 列表。"""
    from app.core.agent_state_store import get_state_store, RedisAgentStateStore
    store = get_state_store()
    if not isinstance(store, RedisAgentStateStore):
        pytest.skip("Redis not available, skipped")
    store.save("u2", "sess_a", "k", 1)
    store.save("u2", "sess_b", "k", 2)
    sessions = store.list_session_ids("u2")
    assert "sess_a" in sessions and "sess_b" in sessions
    store.delete("u2", "sess_a")
    store.delete("u2", "sess_b")
