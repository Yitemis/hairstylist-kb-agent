# -*- coding: utf-8 -*-
"""LLM 响应缓存 + 用户提问幂等。

借鉴 12-factor app：进程内缓存 + 持久化 fallback。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LRUCache:
    """线程安全 LRU 缓存（带 TTL）。"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None
            value, expire_at = self._cache[key]
            if time.time() > expire_at:
                del self._cache[key]
                self.misses += 1
                return None
            self.hits += 1
            # 移到末尾（LRU）
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.time() + self._ttl)
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0.0,
        }


def hash_messages(messages: list[dict], model: str = "") -> str:
    """Stable hash for messages（忽略空字段）。"""
    payload = {"model": model, "messages": messages}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def generate_idempotency_key(user_id: int, message: str, session_id: Optional[str] = None) -> str:
    """生成幂等 key（user_id + message 内容 hash）。"""
    h = hashlib.sha256(f"{user_id}|{message}|{session_id or ''}".encode()).hexdigest()[:16]
    return f"msg_{h}"


# ===================================================================
# 全局实例
# ===================================================================

_llm_cache = None
_idempotency_cache = None


def _get_backend():
    """选择 cache backend: REDIS_URL 设了用 Redis, 否则 LRU (fallback)。"""
    import os
    if os.environ.get("REDIS_URL"):
        try:
            from app.core.cache.redis_cache import RedisCache
            return "redis"
        except ImportError:
            pass
    return "lru"


def get_llm_cache():
    """获取 LLM 缓存 (全局单例)。"""
    global _llm_cache
    if _llm_cache is None:
        backend = _get_backend()
        if backend == "redis":
            from app.core.cache.redis_cache import RedisCache, get_redis_url
            _llm_cache = RedisCache(
                redis_url=get_redis_url(),
                prefix="hairstylist:llm",
                default_ttl=3600,  # 1h
            )
        else:
            _llm_cache = LRUCache(max_size=1000, ttl_seconds=3600)
    return _llm_cache


def get_idempotency_cache():
    """获取幂等缓存 (全局单例)。"""
    global _idempotency_cache
    if _idempotency_cache is None:
        backend = _get_backend()
        if backend == "redis":
            from app.core.cache.redis_cache import RedisCache, get_redis_url
            _idempotency_cache = RedisCache(
                redis_url=get_redis_url(),
                prefix="hairstylist:idem",
                default_ttl=86400,  # 24h
            )
        else:
            _idempotency_cache = LRUCache(max_size=10000, ttl_seconds=86400)
    return _idempotency_cache
