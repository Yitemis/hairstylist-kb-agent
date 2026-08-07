# -*- coding: utf-8 -*-
"""跨进程缓存后端：Redis 替代内存 LRU，session/进程间共享。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 避免循环 import, 延迟到运行时
_RedisCache = None  # 实际类


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class RedisCache:
    """Redis 缓存实现 (异步)。

    借鉴 redis-py 异步客户端 + 12-factor app 配置外置。
    """

    def __init__(self, redis_url: str, prefix: str = "hairstylist",
                 default_ttl: int = 3600, max_size_hint: int = 10000):
        self._url = redis_url
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._max_size_hint = max_size_hint
        self._client = None
        self.hits = 0
        self.misses = 0
        self._connected = False
        self._lock = asyncio.Lock()

    async def _ensure_client(self):
        """懒加载 Redis client (避免启动时就连不上)。"""
        if self._client is not None and self._connected:
            return True
        async with self._lock:
            if self._client is not None and self._connected:
                return True
            try:
                from redis.asyncio import Redis
                self._client = Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                await asyncio.wait_for(self._client.ping(), timeout=2)
                self._connected = True
                logger.info("Redis connected: %s", self._url)
                return True
            except Exception as e:
                logger.warning("Redis connection failed: %s", e)
                self._connected = False
                return False

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        if not await self._ensure_client():
            return None
        try:
            value = await self._client.get(self._key(key))
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            return json.loads(value)
        except Exception as e:
            logger.warning("Redis get failed: %s", e)
            self._connected = False
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not await self._ensure_client():
            return
        try:
            expire = ttl or self._default_ttl
            await self._client.setex(self._key(key), expire, json.dumps(value, ensure_ascii=False))
        except Exception as e:
            logger.warning("Redis set failed: %s", e)
            self._connected = False

    async def delete(self, key: str) -> None:
        if not await self._ensure_client():
            return
        try:
            await self._client.delete(self._key(key))
        except Exception as e:
            logger.warning("Redis delete failed: %s", e)

    async def clear(self, pattern: str = "*") -> int:
        """清空所有 key (按 pattern)。Returns: 删除数量。"""
        if not await self._ensure_client():
            return 0
        try:
            full_pattern = f"{self._prefix}:{pattern}"
            keys = []
            async for k in self._client.scan_iter(match=full_pattern, count=100):
                keys.append(k)
            if keys:
                await self._client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.warning("Redis clear failed: %s", e)
            return 0

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "backend": "redis",
            "url": self._url,
            "connected": self._connected,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0.0,
        }

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
            self._connected = False


def get_redis_url() -> str:
    """从环境变量获取 Redis URL。"""
    return _get_env("REDIS_URL", "redis://localhost:6379/0")
