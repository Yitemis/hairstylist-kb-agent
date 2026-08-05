# -*- coding: utf-8 -*-
"""Model Gateway 测试 - 熔断 / 降级 / 重试 / 缓存。

借鉴 JavaGuide fallback-and-circuit-breaker.md + timeout-and-retry.md。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# 基础导入
from app.core.gateway.model_gateway import (
    ModelGateway, GatewayResult, FallbackStrategy,
    _get_breaker, reset_breakers, _default_fallback, _retry_with_backoff,
    get_model_gateway, CB_THRESHOLD, CB_TIMEOUT,
)
import pybreaker


@pytest.fixture(autouse=True)
def _reset_state():
    """每个测试前重置 breakers（避免测试间污染）。"""
    reset_breakers()
    yield
    reset_breakers()


# ===================================================================
# 基础 - GatewayResult
# ===================================================================

class TestGatewayResult:
    def test_default_values(self):
        from app.core.gateway.model_gateway import GatewayResult
        r = GatewayResult(value="ok")
        assert r.value == "ok"
        assert r.cached is False
        assert r.fallback is False
        assert r.retries == 0


# ===================================================================
# CircuitBreaker - 熔断器
# ===================================================================

class TestCircuitBreaker:
    def test_get_breaker_returns_breaker(self):
        b = _get_breaker("test_cap_1")
        assert b is not None
        assert b.name == "test_cap_1"

    def test_breaker_singleton(self):
        reset_breakers()
        b1 = _get_breaker("test_cap_2")
        b2 = _get_breaker("test_cap_2")
        assert b1 is b2

    def test_reset_breakers(self):
        b1 = _get_breaker("test_cap_3")
        reset_breakers()
        b2 = _get_breaker("test_cap_3")
        assert b1 is not b2

    def test_breaker_opens_after_failures(self):
        reset_breakers()
        b = _get_breaker("test_cap_4")
        for _ in range(CB_THRESHOLD):
            try:
                b.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except (RuntimeError, pybreaker.CircuitBreakerError):
                pass
        # 熔断后状态应该是 open
        assert b.current_state in ("open", "half-open")


# ===================================================================
# 降级策略
# ===================================================================

class TestFallbackStrategies:
    @pytest.mark.asyncio
    async def test_raise_strategy_raises(self):
        with pytest.raises(RuntimeError) as exc:
            await _default_fallback("text_embedding", FallbackStrategy.RAISE)
        assert "unavailable" in str(exc.value)

    @pytest.mark.asyncio
    async def test_empty_strategy_returns_list(self):
        result = await _default_fallback("text_embedding", FallbackStrategy.EMPTY)
        assert result == []

    @pytest.mark.asyncio
    async def test_default_strategy_returns_message(self):
        result = await _default_fallback("text_embedding", FallbackStrategy.DEFAULT)
        assert isinstance(result, str)
        assert "unavailable" in result.lower() or "sorry" in result.lower()


# ===================================================================
# 重试 - 指数退避
# ===================================================================

class TestRetryBackoff:
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_try(self):
        attempts = [0]
        async def fn():
            attempts[0] += 1
            if attempts[0] < 2:
                raise RuntimeError("transient")
            return "ok"
        # patch sleep to be instant
        with patch("asyncio.sleep", new=AsyncMock()):
            result, attempts_used = await _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert attempts_used == 1

    @pytest.mark.asyncio
    async def test_retry_exhausts_then_raises(self):
        async def fn():
            raise RuntimeError("always fail")
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await _retry_with_backoff(fn, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_retry_max_attempts(self):
        attempts = [0]
        async def fn():
            attempts[0] += 1
            raise RuntimeError("boom")
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await _retry_with_backoff(fn, max_retries=2, base_delay=0.01)
        # max_retries=2 means 3 total attempts (initial + 2 retries)
        assert attempts[0] == 3


# ===================================================================
# ModelGateway.call 单元测试 - Mock
# ===================================================================

class TestGatewayCall:
    @pytest.mark.asyncio
    async def test_call_with_disabled_capability_falls_back(self):
        """端点不可用时降级 (raise) - 但 RAISE 模式应该 raise。"""
        from app.embedding.router import Capability
        gw = ModelGateway()
        # Disable text_embedding
        gw.router.disable(Capability.TEXT_EMBEDDING)
        with pytest.raises(RuntimeError):
            r = await gw.call("text_embedding", texts=["hi"], fallback=FallbackStrategy.RAISE)

    @pytest.mark.asyncio
    async def test_call_with_disabled_capability_returns_default(self):
        """端点不可用 + fallback=DEFAULT - 返回默认消息。"""
        from app.embedding.router import Capability
        gw = ModelGateway()
        gw.router.disable(Capability.TEXT_EMBEDDING)
        r = await gw.call("text_embedding", texts=["hi"], fallback=FallbackStrategy.DEFAULT)
        assert r.fallback is True
        assert r.capability == "text_embedding"
        assert "unavailable" in r.value.lower() or "sorry" in r.value.lower()

    @pytest.mark.asyncio
    async def test_call_with_disabled_returns_empty_for_embedding(self):
        """端点不可用 + fallback=EMPTY - embedding 场景返回空列表。"""
        from app.embedding.router import Capability
        gw = ModelGateway()
        gw.router.disable(Capability.MM_EMBEDDING)
        r = await gw.call("mm_embedding", texts=["hi"], fallback=FallbackStrategy.EMPTY)
        assert r.fallback is True
        assert r.value == []


# ===================================================================
# 缓存命中
# ===================================================================

class TestGatewayCache:
    def test_gateway_has_cache(self):
        gw = ModelGateway()
        assert gw.cache is not None
        # LRU 缓存属性
        assert hasattr(gw.cache, "get")
        assert hasattr(gw.cache, "set")

    def test_cache_key_generation(self):
        from app.core.cache.llm_cache import hash_messages
        # 同 messages 同 model = 同 key
        k1 = hash_messages(["hello"], model="m1")
        k2 = hash_messages(["hello"], model="m1")
        assert k1 == k2
        # 不同 model = 不同 key
        k3 = hash_messages(["hello"], model="m2")
        assert k1 != k3


# ===================================================================
# Singleton
# ===================================================================

class TestGatewaySingleton:
    def test_get_model_gateway_singleton(self):
        g1 = get_model_gateway()
        g2 = get_model_gateway()
        assert g1 is g2
