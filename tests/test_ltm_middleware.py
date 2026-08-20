# -*- coding: utf-8 -*-
"""Long-Term Memory Middleware unit tests (P1-2)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.middleware.long_term_memory import (
    LongTermMemoryMiddleware,
    build_facts_injection,
    inject_user_facts,
    load_user_facts,
    extract_and_save_after_chat,
)


class TestBuildFactsInjection:
    def test_empty_facts(self):
        result = build_facts_injection([])
        assert result == ""

    def test_single_fact(self):
        facts = [{"key": "preferred_stylist", "value": "Tony", "confidence": 0.9}]
        result = build_facts_injection(facts)
        assert "preferred_stylist" in result
        assert "Tony" in result

    def test_multiple_facts(self):
        facts = [
            {"key": "preferred_stylist", "value": "Tony", "confidence": 0.9},
            {"key": "allergic_to", "value": "ammonia", "confidence": 1.0},
        ]
        result = build_facts_injection(facts)
        assert "Tony" in result
        assert "ammonia" in result


class TestInjectUserFacts:
    @pytest.mark.asyncio
    async def test_no_facts_returns_original(self):
        with patch("app.rag.middleware.long_term_memory.load_user_facts") as mock_load:
            mock_load.return_value = []
            result = await inject_user_facts(1, "Original system prompt")
            assert result == "Original system prompt"

    @pytest.mark.asyncio
    async def test_with_facts_injects_to_prompt(self):
        with patch("app.rag.middleware.long_term_memory.load_user_facts") as mock_load:
            mock_load.return_value = [
                {"key": "preferred_stylist", "value": "Tony", "confidence": 0.9},
            ]
            result = await inject_user_facts(1, "You are an assistant")
            assert "Tony" in result
            assert "You are an assistant" in result

    @pytest.mark.asyncio
    async def test_max_facts_limit(self):
        facts = [{"key": "k" + str(i), "value": "v" + str(i), "confidence": 0.9} for i in range(50)]
        with patch("app.rag.middleware.long_term_memory.load_user_facts") as mock_load:
            mock_load.return_value = facts
            result = await inject_user_facts(1, "Original", max_facts=5)
            # First 5 facts injected
            for i in range(5):
                assert ("k" + str(i)) in result
            # The 6th fact should NOT be injected
            assert "k5" not in result

    @pytest.mark.asyncio
    async def test_no_user_id_returns_original(self):
        result = await inject_user_facts(0, "Original")
        assert result == "Original"


class TestLongTermMemoryMiddleware:
    def test_init(self):
        mw = LongTermMemoryMiddleware()
        assert mw.max_facts == 20
        assert mw.auto_extract is True

    def test_init_custom(self):
        mw = LongTermMemoryMiddleware(max_facts=10, auto_extract=False)
        assert mw.max_facts == 10
        assert mw.auto_extract is False

    @pytest.mark.asyncio
    async def test_on_reasoning_no_user_id(self):
        mw = LongTermMemoryMiddleware()
        ctx = MagicMock()
        del ctx.user_id
        next_fn = AsyncMock(return_value="result")
        result = await mw.on_reasoning(ctx, next_fn)
        next_fn.assert_called_once()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_on_reasoning_no_system_prompt(self):
        mw = LongTermMemoryMiddleware()
        ctx = MagicMock()
        ctx.user_id = 1
        ctx.system_prompt = ""
        next_fn = AsyncMock(return_value="result")
        result = await mw.on_reasoning(ctx, next_fn)
        next_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_reasoning_injects(self):
        mw = LongTermMemoryMiddleware()
        ctx = MagicMock()
        ctx.user_id = 1
        ctx.system_prompt = "You are an assistant"

        with patch("app.rag.middleware.long_term_memory.inject_user_facts") as mock_inject:
            mock_inject.return_value = "Injected" + chr(10) + chr(10) + "You are an assistant"
            next_fn = AsyncMock(return_value="result")
            result = await mw.on_reasoning(ctx, next_fn)
            mock_inject.assert_called_once()
            assert ctx.system_prompt.startswith("Injected")
            assert result == "result"

    @pytest.mark.asyncio
    async def test_on_reply_no_extract(self):
        mw = LongTermMemoryMiddleware(auto_extract=False)
        ctx = MagicMock()
        ctx.user_id = 1
        ctx.last_user_message = "I like Tony"
        ctx.last_ai_message = "OK"
        next_fn = AsyncMock(return_value="response")
        result = await mw.on_reply(ctx, next_fn)
        next_fn.assert_called_once()
        assert result == "response"

    @pytest.mark.asyncio
    async def test_on_reply_with_extract_schedules_task(self):
        mw = LongTermMemoryMiddleware(auto_extract=True)
        ctx = MagicMock()
        ctx.user_id = 1
        ctx.last_user_message = "I prefer Tony stylist"
        ctx.last_ai_message = "Noted!"
        next_fn = AsyncMock(return_value="response")
        with patch("asyncio.create_task") as mock_create:
            result = await mw.on_reply(ctx, next_fn)
            next_fn.assert_called_once()
            mock_create.assert_called_once()
            assert result == "response"

    @pytest.mark.asyncio
    async def test_on_reply_no_messages_skips_extract(self):
        mw = LongTermMemoryMiddleware(auto_extract=True)
        ctx = MagicMock()
        ctx.user_id = 1
        ctx.last_user_message = ""
        ctx.last_ai_message = ""
        next_fn = AsyncMock(return_value="response")
        with patch("asyncio.create_task") as mock_create:
            result = await mw.on_reply(ctx, next_fn)
            mock_create.assert_not_called()


class TestLoadUserFactsFallback:
    @pytest.mark.asyncio
    async def test_db_failure_returns_empty(self):
        with patch("app.core.long_term_memory.get_user_facts") as mock:
            mock.side_effect = Exception("DB down")
            result = await load_user_facts(1)
            assert result == []


class TestExtractAndSaveFallback:
    @pytest.mark.asyncio
    async def test_extraction_failure_returns_zero(self):
        with patch("app.core.long_term_memory.extract_and_save_facts") as mock:
            mock.side_effect = Exception("LLM down")
            result = await extract_and_save_after_chat(1, "msg", "response")
            assert result == 0
