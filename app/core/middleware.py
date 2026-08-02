# -*- coding: utf-8 -*-
"""中间件系统：借鉴 AgentScope 2.0 的 MiddlewareBase。

核心思想：AOP 拦截，每个中间件可在执行前后操作。

5 个拦截点（从外到内）：
- onAgent:       整个 Agent 执行（用于耗时统计、trace ID）
- onReasoning:   推理阶段（用于查询改写、context 增强）
- onActing:      行动阶段（用于工具权限、限流）
- onModelCall:   底层模型调用（用于 LLM 缓存、降级）
- onSystemPrompt: 管道式（用于叠加多个提示词变换）

洋葱模式 vs 管道模式：
- 洋葱：每个中间件在"调下一个"前后可操作（适合日志/计时/鉴权）
- 管道：每个中间件把前一个的输出当输入（适合叠加变换）
"""
from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareContext:
    """中间件上下文：贯穿整个请求的生命周期。"""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: int | None = None
    session_id: str | None = None
    intent: str | None = None
    started_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class MiddlewareBase(ABC):
    """中间件基类（参考 AgentScope 2.0 的 MiddlewareBase）。"""

    name: str = "BaseMiddleware"

    @abstractmethod
    async def on_agent(
        self,
        ctx: MiddlewareContext,
        next_fn: Callable,
    ) -> Any:
        """最外层：拦截整个 Agent 调用。"""
        ...

    async def on_reasoning(
        self,
        ctx: MiddlewareContext,
        next_fn: Callable,
    ) -> Any:
        """推理阶段：默认透传。"""
        return await next_fn()

    async def on_acting(
        self,
        ctx: MiddlewareContext,
        next_fn: Callable,
    ) -> Any:
        """行动阶段：默认透传。"""
        return await next_fn()


class LoggingMiddleware(MiddlewareBase):
    """日志中间件：记录每次 chat 调用的完整生命周期。"""

    name = "Logging"

    async def on_agent(self, ctx: MiddlewareContext, next_fn: Callable) -> Any:
        logger.info(
            "[trace=%s] start chat: user=%s session=%s",
            ctx.trace_id, ctx.user_id, ctx.session_id,
        )
        try:
            result = await next_fn()
            elapsed = int((time.time() - ctx.started_at) * 1000)
            logger.info(
                "[trace=%s] end chat: mode=%s intent=%s elapsed=%dms",
                ctx.trace_id, ctx.metadata.get("mode"), ctx.intent, elapsed,
            )
            return result
        except Exception as e:
            elapsed = int((time.time() - ctx.started_at) * 1000)
            logger.error(
                "[trace=%s] chat failed after %dms: %s",
                ctx.trace_id, elapsed, e,
            )
            raise

    async def on_reasoning(self, ctx: MiddlewareContext, next_fn: Callable) -> Any:
        if ctx.intent is None:
            ctx.intent = "unknown"
        return await next_fn()


class RateLimitMiddleware(MiddlewareBase):
    """限流中间件：每个用户的每分钟请求数限制。"""

    name = "RateLimit"

    def __init__(self, per_minute: int = 60) -> None:
        self.per_minute = per_minute
        # user_id -> [timestamps]
        self._buckets: dict[int, list[float]] = {}

    async def on_agent(self, ctx: MiddlewareContext, next_fn: Callable) -> Any:
        if ctx.user_id is None:
            return await next_fn()
        now = time.time()
        bucket = [t for t in self._buckets.get(ctx.user_id, []) if now - t < 60]
        if len(bucket) >= self.per_minute:
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        bucket.append(now)
        self._buckets[ctx.user_id] = bucket
        return await next_fn()


# 全局中间件链（按顺序执行）
_middlewares: list[MiddlewareBase] = []


def register_middleware(mw: MiddlewareBase) -> None:
    """注册一个中间件。"""
    _middlewares.append(mw)
    logger.info("中间件已注册: %s", mw.name)


def get_middlewares() -> list[MiddlewareBase]:
    """获取已注册的中间件列表。"""
    return _middlewares


def reset_middlewares() -> None:
    """重置（测试用）。"""
    _middlewares.clear()


def build_default_middlewares() -> None:
    """注册默认中间件（日志 + 限流）。"""
    reset_middlewares()
    register_middleware(LoggingMiddleware())
    register_middleware(RateLimitMiddleware(per_minute=120))


async def run_with_middlewares(
    ctx: MiddlewareContext,
    core_fn: Callable,
) -> Any:
    """用洋葱链包装执行 core_fn。

    等价于 middlewares[A, B, C] 嵌套调用 core_fn。
    """
    chain = core_fn
    # 从后往前构建洋葱
    for mw in reversed(_middlewares):
        prev_chain = chain
        chain = lambda c=prev_chain, m=mw: m.on_agent(ctx, c)
    return await chain()


# 模块加载时注册默认中间件
build_default_middlewares()
