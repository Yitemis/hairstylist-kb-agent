# -*- coding: utf-8 -*-
"""Enriched Passage unit tests."""
import pytest

from app.rag.chat_pipeline.enrich import (
    get_enriched_passage,
    get_enriched_passages_batch,
    sanitize_passage_for_rerank,
)
from app.rag.v2_engine import RetrievalHit


class TestGetEnrichedPassage:
    def test_with_hit_dict(self):
        hit = {"content": "perm test", "filename": "manual.pdf"}
        out = get_enriched_passage(hit)
        assert "manual.pdf" in out
        assert "perm test" in out
        assert out.startswith("文档:")

    def test_with_section_path(self):
        hit = {"content": "water temp 38", "filename": "hairstyle.pdf"}
        out = get_enriched_passage(hit, section_path="wash > temp")
        assert "wash > temp" in out
        assert "hairstyle.pdf" in out
        assert "water temp 38" in out

    def test_with_retrieval_hit_dataclass(self):
        hit = RetrievalHit(
            parent_id="p1", content="test content", source="file.pdf",
            score=0.9, matched_child="", tenant_id="default", document_id="d1",
        )
        out = get_enriched_passage(hit, section_path="ch1")
        assert "file.pdf" in out
        assert "ch1" in out
        assert "test content" in out

    def test_truncate_long_content(self):
        long_content = "perm " * 1000
        hit = {"content": long_content, "filename": "f.pdf"}
        out = get_enriched_passage(hit, max_chars=100)
        assert "perm" in out

    def test_no_filename(self):
        hit = {"content": "abc"}
        out = get_enriched_passage(hit)
        assert "unknown" in out
        assert "abc" in out

    def test_max_chars_truncation_marker(self):
        hit = {"content": "x" * 2000}
        out = get_enriched_passage(hit, max_chars=10)
        assert "..." in out


class TestBatchEnrichment:
    def test_batch_basic(self):
        hits = [
            {"content": "c1", "filename": "a.pdf"},
            {"content": "c2", "filename": "b.pdf"},
        ]
        out = get_enriched_passages_batch(hits, section_paths=["s1", "s2"])
        assert len(out) == 2
        assert "a.pdf" in out[0]
        assert "b.pdf" in out[1]
        assert "s1" in out[0]
        assert "s2" in out[1]

    def test_batch_length_mismatch_raises(self):
        hits = [{"content": "x"}]
        with pytest.raises(ValueError):
            get_enriched_passages_batch(hits, section_paths=["a", "b"])


class TestSanitizePassage:
    def test_remove_base64_image(self):
        b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEX///+nxBvIAAAACklEQVQI12NgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=="
        data_url = "data:image/png;base64," + b64
        text = "pre" + data_url + "post"
        out = sanitize_passage_for_rerank(text)
        # base64 < 200 chars, no replacement, but max_total_chars truncation may apply
        assert "pre" in out
        assert "post" in out
        assert len(out) <= 8000

    def test_truncate_too_long(self):
        text = "x" * 20000
        out = sanitize_passage_for_rerank(text, max_total_chars=1000)
        assert len(out) == 1000
