# -*- coding: utf-8 -*-
"""错误分类 + 指数退避重试装饰器。

借鉴 AgentScope 的 ReActConfig.max_retries + retry_delay 模式。
对网络错误、LLM 临时故障自动重试；对业务错误立即失败。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorClass(str, Enum):
    """错误分类。"""
    TRANSIENT = "transient"        # 临时错误（网络超时、LLM 限流、连接重置）→ 重试
    RATE_LIMIT = "rate_limit"       # 限流 → 退避重试
    PERMANENT = "permanent"        # 永久错误（参数错、权限错）→ 立即失败
    UNKNOWN = "unknown"            # 未知 → 默认重试


# 哪些异常是 transient
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,  # 网络层错误
)


# 哪些异常是 permanent
PERMANENT_EXCEPTIONS = (
    ValueError,
    TypeError,
    KeyError,
    PermissionError,
    FileNotFoundError,
)


def classify_error(exc: BaseException) -> ErrorClass:
    """把异常分类。"""
    err_str = str(exc).lower()
    # 限流关键字
    if any(k in err_str for k in ("rate limit", "429", "too many requests", "限流")):
        return ErrorClass.RATE_LIMIT
    # 临时错误关键字
    if any(k in err_str for k in ("timeout", "connection", "reset", "refused", "unavailable", "503", "502", "504")):
        return ErrorClass.TRANSIENT
    # 已知类型
    if isinstance(exc, TRANSIENT_EXCEPTIONS):
        return ErrorClass.TRANSIENT
    if isinstance(exc, PERMANENT_EXCEPTIONS):
        return ErrorClass.PERMANENT
    return ErrorClass.UNKNOWN


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,),
):
    """异步指数退避重试装饰器。

    Usage:
        @async_retry(max_attempts=3)
        async def call_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    cls = classify_error(e)
                    if cls == ErrorClass.PERMANENT:
                        logger.error("[%s] permanent error, no retry: %s", func.__name__, e)
                        raise
                    if attempt >= max_attempts:
                        logger.error("[%s] all %d attempts failed: %s", func.__name__, max_attempts, e)
                        raise
                    # 计算退避时间（指数 + 抖动）
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay += random.uniform(0, 0.5)
                    logger.warning(
                        "[%s] attempt %d/%d failed (%s), retry in %.2fs: %s",
                        func.__name__, attempt, max_attempts, cls.value, delay, e,
                    )
                    await asyncio.sleep(delay)
            # 不应该到这里
            raise last_exc  # type: ignore
        return wrapper
    return decorator
