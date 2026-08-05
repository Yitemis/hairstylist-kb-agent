# -*- coding: utf-8 -*-
"""Model Gateway - unified AI model invocation entry point.

Inspired by OpenRouter / Portkey / AWS Bedrock multi-model routing.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

import pybreaker

from app.core.cache.llm_cache import get_llm_cache, hash_messages
from app.core.metrics import llm_cache_total
from app.embedding.router import Capability, ModelRouter, get_endpoint, get_model_router

logger = logging.getLogger(__name__)

CB_THRESHOLD = 5
CB_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0


class FallbackStrategy(str, Enum):
    RAISE = "raise"
    CACHE = "cache"
    DEFAULT = "default"
    EMPTY = "empty"


@dataclass
class GatewayResult:
    value: Any = None
    cached: bool = False
    fallback: bool = False
    retries: int = 0
    elapsed_ms: int = 0
    capability: Optional[str] = None
    error: Optional[str] = None


_breakers = {}


def _get_breaker(capability):
    if capability not in _breakers:
        _breakers[capability] = pybreaker.CircuitBreaker(
            fail_max=CB_THRESHOLD, reset_timeout=CB_TIMEOUT, name=capability)
    return _breakers[capability]


def reset_breakers():
    _breakers.clear()


async def _default_fallback(capability, strategy):
    if strategy == FallbackStrategy.RAISE:
        raise RuntimeError(str(capability) + " unavailable (circuit open)")
    elif strategy == FallbackStrategy.EMPTY:
        return []
    elif strategy == FallbackStrategy.DEFAULT:
        return "Sorry, AI service temporarily unavailable."
    return None


async def _retry_with_backoff(fn, max_retries=MAX_RETRIES,
                             base_delay=RETRY_BASE_DELAY, max_delay=RETRY_MAX_DELAY):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = await fn()
            return result, attempt
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                delay = delay * (0.5 + random.random() * 0.5)
                logger.warning("Retry %d/%d", attempt + 1, max_retries)
                await asyncio.sleep(delay)
    raise last_error


class ModelGateway:
    def __init__(self):
        self.router = get_model_router()
        self.cache = get_llm_cache()

    async def call(self, capability, *, use_cache=True, max_retries=MAX_RETRIES,
                   fallback=FallbackStrategy.RAISE,
                   texts=None, messages=None, query=None, documents=None, image_blocks=None):
        cap = capability.value if isinstance(capability, Capability) else capability
        start = time.time()
        endpoint = self.router.get_endpoint(Capability(cap))
        if endpoint is None:
            value = await _default_fallback(cap, fallback)
            return GatewayResult(value=value, fallback=True, capability=cap,
                error=str(cap) + " unavailable",
                elapsed_ms=int((time.time() - start) * 1000))
        cache_key = None
        if use_cache:
            if texts:
                cache_key = hash_messages(texts, model=endpoint.model)
            elif messages:
                cache_key = hash_messages(messages, model=endpoint.model)
            elif query and documents:
                cache_key = hashlib.sha256(
                    (query + "|" + endpoint.model + "|" + "|".join(documents)).encode()
                ).hexdigest()[:32]
            if cache_key:
                cached = self.cache.get(cache_key)
                if cached is not None:
                    llm_cache_total.labels(result="hit").inc()
                    return GatewayResult(value=cached, cached=True, capability=cap,
                        elapsed_ms=int((time.time() - start) * 1000))
                llm_cache_total.labels(result="miss").inc()
        breaker = _get_breaker(cap)
        async def _do_call():
            return await self._invoke(cap=cap, endpoint=endpoint,
                texts=texts, messages=messages, query=query, documents=documents,
                image_blocks=image_blocks)
        retries = 0
        error_msg = None
        try:
            if breaker.current_state == "open":
                raise pybreaker.CircuitBreakerError("circuit open")
            value, retries = await _retry_with_backoff(_do_call, max_retries=max_retries)
        except (pybreaker.CircuitBreakerError, Exception) as e:
            error_msg = type(e).__name__ + ": " + str(e)[:200]
            logger.error("Model Gateway call failed: %s", error_msg)
            value = await _default_fallback(cap, fallback)
            return GatewayResult(value=value, fallback=True, retries=retries,
                capability=cap, error=error_msg,
                elapsed_ms=int((time.time() - start) * 1000))
        if use_cache and cache_key and value is not None:
            self.cache.set(cache_key, value)
        return GatewayResult(value=value, retries=retries, capability=cap,
            elapsed_ms=int((time.time() - start) * 1000))

    async def _invoke(self, cap, endpoint, texts=None, messages=None, query=None,
                      documents=None, image_blocks=None):
        if cap in ("text_embedding", "mm_embedding"):
            return await self._invoke_embedding(cap, endpoint, texts, image_blocks)
        elif cap in ("chat", "mm_chat"):
            return await self._invoke_chat(endpoint, messages, image_blocks)
        elif cap == "rerank":
            return await self._invoke_rerank(endpoint, query, documents)
        raise ValueError("Unknown capability: " + str(cap))

    async def _invoke_embedding(self, cap, endpoint, texts, image_blocks=None):
        from app.embedding import build_embedding_model
        from agentscope.message import TextBlock, DataBlock, Base64Source
        model = build_embedding_model(capability=cap)
        blocks = []
        if texts:
            blocks.extend([TextBlock(text=t) for t in texts])
        if image_blocks:
            for img in image_blocks:
                url = img.get("url", "")
                if url.startswith("data:"):
                    mime = url.split(";")[0].split(":")[1]
                    b64 = url.split(",", 1)[1]
                    blocks.append(DataBlock(source=Base64Source(data=b64, media_type=mime)))
        resp = await model(blocks)
        return resp.embeddings

    async def _invoke_chat(self, endpoint, messages, image_blocks=None):
        from app.core.model_factory import get_model
        from agentscope.message import TextBlock, UserMsg, DataBlock, Base64Source
        model = get_model("chat")
        as_msgs = []
        for m in messages:
            if m["role"] == "system":
                as_msgs.append(UserMsg(name="system", content=[TextBlock(text=m["content"])]))
            elif m["role"] == "user":
                content = []
                if isinstance(m.get("content"), str):
                    content.append(TextBlock(text=m["content"]))
                elif isinstance(m.get("content"), list):
                    for block in m["content"]:
                        if block.get("type") == "text":
                            content.append(TextBlock(text=block["text"]))
                        elif block.get("type") == "image_url":
                            url = block["image_url"]["url"]
                            if url.startswith("data:"):
                                mime = url.split(";")[0].split(":")[1]
                                b64 = url.split(",", 1)[1]
                                content.append(DataBlock(source=Base64Source(data=b64, media_type=mime)))
                as_msgs.append(UserMsg(name="user", content=content))
        return await model(as_msgs, stream=False)

    async def _invoke_rerank(self, endpoint, query, documents):
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(endpoint.base_url + "/rerank",
                headers={"Authorization": "Bearer " + endpoint.api_key},
                json={"model": endpoint.model, "query": query, "documents": documents})
            r.raise_for_status()
            return r.json().get("results", [])


_gateway = None


def get_model_gateway():
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway