# -*- coding: utf-8 -*-
"""SSE chat unit tests (P1-1)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.events import ChatEvent, ChatEventBus


class FakeUser:
    def __init__(self, id=1, role="user"):
        self.id = id
        self.role = role


class TestChatEventBus:
    def test_event_to_sse(self):
        evt = ChatEvent(event="text", data={"delta": "hi"})
        sse = evt.to_sse()
        assert sse.startswith("event: text")
        assert "data: " in sse
        data_line = [l for l in sse.split(chr(10)) if l.startswith("data:")][0]
        assert json.loads(data_line[6:]) == {"delta": "hi"}

    def test_event_sse_format(self):
        evt = ChatEvent(event="done", data={"answer": "x"})
        sse = evt.to_sse()
        assert sse.endswith(chr(10) + chr(10))
        lines = sse.strip().split(chr(10))
        assert any(l.startswith("event:") for l in lines)
        assert any(l.startswith("data:") for l in lines)


class TestEventStream:
    @pytest.mark.asyncio
    async def test_basic_stream(self):
        bus = ChatEventBus()
        bus.push("text", {"delta": "hello"})
        bus.push("done", {"answer": "hello"})
        events = []
        async for sse in bus.stream():
            events.append(sse)
        assert len(events) == 2
        assert "event: text" in events[0]
        assert "event: done" in events[1]

    @pytest.mark.asyncio
    async def test_stream_terminates_on_close(self):
        bus = ChatEventBus()
        bus.push("text", {"delta": "a"})
        bus.close()
        events = []
        async for sse in bus.stream():
            events.append(sse)
        assert len(events) == 1
        assert "event: text" in events[0]


class TestSSERunChatPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_pushes_all_stages(self):
        from app.server.routers.chat_stream import _run_chat_pipeline
        bus = ChatEventBus()
        user = FakeUser(id=1, role="user")

        async def mock_run(chat_ctx):
            chat_ctx.rewritten_queries = ["test"]
            chat_ctx.raw_hits = [{"parent_id": "p1", "score": 0.9, "filename": "m.pdf"}]
            chat_ctx.reranked_hits = [{"parent_id": "p1", "score": 0.95, "rerank_score": 0.95, "document_id": "d1"}]
            chat_ctx.final_answer = "answer"
            chat_ctx.sources = [{"document_id": "d1", "score": 0.95}]
            return chat_ctx

        with patch("app.services.chat_service.get_chat_pipeline") as mock_pipeline:
            mock_pipeline.return_value.run = mock_run
            with patch("app.db.session.async_session_maker") as mock_sm:
                mock_session = AsyncMock()
                mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=[])
                mock_session.scalars = AsyncMock(return_value=mock_scalars)
                mock_session.commit = AsyncMock()
                mock_session.add = MagicMock()
                await _run_chat_pipeline("test", user, bus)

        all_events = []
        while not bus._queue.empty():
            evt = bus._queue.get_nowait()
            if evt is None:
                break
            all_events.append(evt)
        event_types = [e.event for e in all_events]
        assert "intent" in event_types
        assert "thinking" in event_types
        assert "search" in event_types
        assert "text" in event_types
        assert "sources" in event_types
        assert "done" in event_types

    @pytest.mark.asyncio
    async def test_pipeline_error_pushes_error_event(self):
        from app.server.routers.chat_stream import _run_chat_pipeline
        bus = ChatEventBus()
        user = FakeUser(id=1, role="user")

        async def mock_run_failing(chat_ctx):
            raise RuntimeError("Pipeline failed")

        with patch("app.services.chat_service.get_chat_pipeline") as mock_pipeline:
            mock_pipeline.return_value.run = mock_run_failing
            with patch("app.db.session.async_session_maker") as mock_sm:
                mock_session = AsyncMock()
                mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=[])
                mock_session.scalars = AsyncMock(return_value=mock_scalars)
                await _run_chat_pipeline("test", user, bus)

        all_events = []
        while not bus._queue.empty():
            evt = bus._queue.get_nowait()
            if evt is None:
                break
            all_events.append(evt)
        event_types = [e.event for e in all_events]
        assert "error" in event_types

    @pytest.mark.asyncio
    async def test_text_event_streaming(self):
        from app.server.routers.chat_stream import _run_chat_pipeline
        bus = ChatEventBus()
        user = FakeUser(id=1, role="user")
        long_answer = "x" * 100

        async def mock_run(chat_ctx):
            chat_ctx.rewritten_queries = ["q"]
            chat_ctx.raw_hits = []
            chat_ctx.reranked_hits = []
            chat_ctx.final_answer = long_answer
            chat_ctx.sources = []
            return chat_ctx

        with patch("app.services.chat_service.get_chat_pipeline") as mock_pipeline:
            mock_pipeline.return_value.run = mock_run
            with patch("app.db.session.async_session_maker") as mock_sm:
                mock_session = AsyncMock()
                mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sm.return_value.__aexit__ = AsyncMock(return_value=None)
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=[])
                mock_session.scalars = AsyncMock(return_value=mock_scalars)
                mock_session.commit = AsyncMock()
                mock_session.add = MagicMock()
                await _run_chat_pipeline("test", user, bus)

        text_events = []
        while not bus._queue.empty():
            evt = bus._queue.get_nowait()
            if evt is None:
                break
            if evt.event == "text":
                text_events.append(evt)
        assert len(text_events) == 10
        for evt in text_events:
            assert len(evt.data["delta"]) == 10


class TestSSEResponseFormat:
    def test_sse_event_format(self):
        evt = ChatEvent(event="text", data={"delta": "test"})
        sse = evt.to_sse()
        lines = sse.split(chr(10))
        assert lines[0] == "event: text"
        assert lines[1].startswith("data: ")
        assert lines[2] == ""
        assert lines[3] == ""

    def test_sse_data_is_valid_json(self):
        evt = ChatEvent(event="done", data={"answer": "a", "score": 0.9})
        sse = evt.to_sse()
        data_line = [l for l in sse.split(chr(10)) if l.startswith("data:")][0]
        parsed = json.loads(data_line[6:])
        assert parsed["answer"] == "a"
        assert parsed["score"] == 0.9
