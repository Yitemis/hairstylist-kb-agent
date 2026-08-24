# -*- coding: utf-8 -*-
"""KnowledgeUpdater 单测 (Harness v2 sec 7.2)."""
import pytest

from app.rag.knowledge_updater import (
    ChangeEvent, UpdateResult, KnowledgeUpdater, get_knowledge_updater,
)


class TestComputeHash:
    def test_same_content_same_hash(self):
        h1 = KnowledgeUpdater.compute_hash("hello world")
        h2 = KnowledgeUpdater.compute_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content_different_hash(self):
        h1 = KnowledgeUpdater.compute_hash("hello")
        h2 = KnowledgeUpdater.compute_hash("world")
        assert h1 != h2

    def test_empty_content(self):
        h = KnowledgeUpdater.compute_hash("")
        assert len(h) == 64

    def test_none_content(self):
        h = KnowledgeUpdater.compute_hash(None)
        assert len(h) == 64


class TestChangeEvent:
    def test_default_values(self):
        event = ChangeEvent(
            document_id="d1", content="c", filename="f.md", tenant_id="t1",
        )
        assert event.audience == "all"
        assert event.category == "general"
        assert event.chunk_size == 800
        assert event.chunk_overlap == 80
        assert event.embedding_model == "BAAI/bge-large-zh-v1.5"
        assert event.embedding_model_version == "1.0"
        assert event.chunk_strategy == "smart"
        assert event.actor_id is None
        assert event.actor_type == "system"


class TestUpdateResult:
    def test_default_values(self):
        r = UpdateResult(action="created", document_id="d1")
        assert r.action == "created"
        assert r.document_id == "d1"
        assert r.version_id == 0
        assert r.content_hash == ""
        assert r.parents == 0
        assert r.children == 0
        assert r.error is None

    def test_error_result(self):
        r = UpdateResult(action="error", document_id="d1", error="boom")
        assert r.action == "error"
        assert r.error == "boom"


class TestGetKnowledgeUpdater:
    def test_singleton(self):
        u1 = get_knowledge_updater()
        u2 = get_knowledge_updater()
        assert u1 is u2

    def test_returns_knowledge_updater(self):
        u = get_knowledge_updater()
        assert isinstance(u, KnowledgeUpdater)
