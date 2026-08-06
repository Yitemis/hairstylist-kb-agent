# -*- coding: utf-8 -*-
"""Redis 缓存测试 (mock, 不需真 Redis).

借鉴 JavaGuide + 12-factor app:
- 自动 backend 选择 (Redis 优先, fallback LRU)
- 跨进程共享 (生产)
- 异步 API
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.core.cache.llm_cache import (
    LRUCache, hash_messages, generate_idempotency_key,
    get_llm_cache, get_idempotency_cache, _get_backend,
)
from app.core.cache.redis_cache import RedisCache, get_redis_url


# ===================================================================
# LRUCache (向后兼容)
# ===================================================================

def test_lru_cache_basic():
    c = LRUCache(max_size=10, ttl_seconds=60)
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("missing") is None


# ===================================================================
# Backend 选择
# ===================================================================

def test_backend_no_redis_url():
    """没 REDIS_URL → fallback LRU。"""
    with patch.dict("os.environ", {}, clear=True):
        assert _get_backend() == "lru"


def test_backend_with_redis_url():
    """有 REDIS_URL → redis。"""
    with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
        assert _get_backend() == "redis"


def test_get_llm_cache_lru_fallback():
    """默认 LRU。"""
    with patch.dict("os.environ", {}, clear=True):
        import app.core.cache.llm_cache as m
        m._llm_cache = None
        c = m.get_llm_cache()
        assert isinstance(c, LRUCache)
        assert c._max_size == 1000


def test_get_idempotency_cache_lru_fallback():
    with patch.dict("os.environ", {}, clear=True):
        import app.core.cache.llm_cache as m
        m._idempotency_cache = None
        c = m.get_idempotency_cache()
        assert isinstance(c, LRUCache)
        assert c._max_size == 10000


# ===================================================================
# RedisCache 单元测试 (mock redis)
# ===================================================================

class FakeRedis:
    _shared = None  # 单例

    def __init__(self):
        self.data = {}
        self.expires = {}

    async def get(self, key):
        import time
        if key in self.expires and time.time() > self.expires[key]:
            return None
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        import time
        self.data[key] = value
        self.expires[key] = time.time() + ttl

    async def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)
            self.expires.pop(k, None)

    async def ping(self):
        return True

    async def scan_iter(self, match=None, count=100):
        import fnmatch
        for k in list(self.data.keys()):
            if match is None or fnmatch.fnmatchcase(k, match):
                yield k

    async def close(self):
        pass


class FakeRedisModule:
    @staticmethod
    def from_url(url, **kwargs):
        if FakeRedis._shared is None:
            FakeRedis._shared = FakeRedis()
        return FakeRedis._shared


@pytest.mark.asyncio
async def test_redis_cache_set_get():
    """基本 set/get。"""
    cache = RedisCache("redis://localhost:6379/0")
    with patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
        await cache.set("k1", {"v": 1}, ttl=60)
        v = await cache.get("k1")
        assert v == {"v": 1}
        assert cache.hits == 1


@pytest.mark.asyncio
async def test_redis_cache_get_missing():
    cache = RedisCache("redis://localhost:6379/0")
    with patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
        v = await cache.get("missing")
        assert v is None
        assert cache.misses == 1


@pytest.mark.asyncio
async def test_redis_cache_delete():
    cache = RedisCache("redis://localhost:6379/0")
    with patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
        await cache.set("k1", "v1", ttl=60)
        await cache.delete("k1")
        assert await cache.get("k1") is None


@pytest.mark.asyncio
async def test_redis_cache_clear():
    cache = RedisCache("redis://localhost:6379/0", prefix="test")
    with patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
        await cache.set("k1", "v1", ttl=60)
        await cache.set("k2", "v2", ttl=60)
        n = await cache.clear("*")
        assert n == 2
        assert await cache.get("k1") is None
        assert await cache.get("k2") is None


@pytest.mark.asyncio
async def test_redis_cache_connection_failure():
    """Redis 连不上时 graceful fallback。"""
    cache = RedisCache("redis://invalid:6379/0")

    async def fail_ping():
        raise ConnectionError("connect failed")
    with patch("redis.asyncio.Redis.from_url") as mock_factory:
        mock_client = MagicMock()
        mock_client.ping = fail_ping
        mock_factory.return_value = mock_client
        # 静默失败, 不抛
        v = await cache.get("k")
        assert v is None
        assert cache._connected is False


@pytest.mark.asyncio
async def test_redis_cache_namespace():
    """不同 prefix 隔离 namespace。"""
    c1 = RedisCache("redis://localhost:6379/0", prefix="a")
    c2 = RedisCache("redis://localhost:6379/0", prefix="b")
    with patch("redis.asyncio.Redis.asyncio.Redis.from_url", FakeRedisModule.from_url) if False else patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
        await c1.set("key", "value_a", ttl=60)
        await c2.set("key", "value_b", ttl=60)
        assert await c1.get("key") == "value_a"
        assert await c2.get("key") == "value_b"


def test_get_redis_url_default():
    """默认 URL (无 env)。"""
    with patch.dict("os.environ", {}, clear=True):
        assert get_redis_url() == "redis://localhost:6379/0"


def test_get_redis_url_from_env():
    with patch.dict("os.environ", {"REDIS_URL": "redis://custom:6380/2"}):
        assert get_redis_url() == "redis://custom:6380/2"


# ===================================================================
# 端到端 - LLM 缓存用 Redis
# ===================================================================

@pytest.mark.asyncio
async def test_llm_cache_via_redis():
    """当 REDIS_URL 存在时, get_llm_cache() 返回 RedisCache。"""
    with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
        import app.core.cache.llm_cache as m
        m._llm_cache = None
        with patch("redis.asyncio.Redis.from_url", FakeRedisModule.from_url):
            c = m.get_llm_cache()
            assert isinstance(c, RedisCache)
            await c.set("test_key", {"answer": "hi"}, ttl=60)
            assert await c.get("test_key") == {"answer": "hi"}
