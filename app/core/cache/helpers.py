"""Cache helpers (sync/async 兼容, 不被 FastAPI 注册为路由)."""
from __future__ import annotations

import inspect
from typing import Any, Optional


async def cache_get(cache: Any, key: str) -> Optional[Any]:
    result = cache.get(key)
    if inspect.isawaitable(result):
        return await result
    return result


async def cache_set(cache: Any, key: str, value: Any) -> None:
    result = cache.set(key, value)
    if inspect.isawaitable(result):
        return await result
    return result
