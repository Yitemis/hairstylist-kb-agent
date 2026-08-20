# -*- coding: utf-8 -*-
"""Doc Profiler + 3-Tier strategy unit tests."""
import pytest

from app.rag.chunkers.profiler import DocProfile, profile_document
from app.rag.chunkers.strategy import (
    chunk_with_tier,
    explain_tier_choice,
    profile_and_select,
    select_tier,
)


class TestProfileDocument:
    def test_empty_doc(self):
        p = profile_document("")
        assert p.total_chars == 0
        assert p.total_lines == 0
        assert p.recommended_tier == 3

    def test_md_heading_counts(self):
        content = "# H1\n## H2\n## H2 again\n### H3\n#### H4\nbody content"
        p = profile_document(content)
        assert p.md_heading_counts.get(1) == 1
        assert p.md_heading_counts.get(2) == 2
        assert p.md_heading_counts.get(3) == 1
        assert p.md_heading_counts.get(4) == 1

    def test_table_detection(self):
        content = "| col1 | col2 |\n| --- | --- |\n| a   | b   |\n| c   | d   |"
        p = profile_document(content)
        assert p.has_tables is True
        assert p.table_line_count >= 4

    def test_no_table(self):
        p = profile_document("plain text, no tables")
        assert p.has_tables is False

    def test_code_block_detection(self):
        content = "preface\n```python\nprint('hi')\n```\nepilogue"
        p = profile_document(content)
        assert p.has_code is True
        assert p.code_block_count == 1

    def test_mermaid_detection(self):
        content = "diagram:\n```mermaid\ngraph TD\nA-->B\n```"
        p = profile_document(content)
        assert p.has_mermaid is True

    def test_equation_detection(self):
        content = "formula: $$E = mc^2$$ and $$a^2 + b^2 = c^2$$"
        p = profile_document(content)
        assert p.has_equations is True
        assert p.equation_count == 2

    def test_numbered_sections(self):
        content = "1.1 intro\n1.2 detail\n1.3 conclusion\n2.1 chapter2"
        p = profile_document(content)
        assert p.numbered_section_count >= 3

    def test_form_feed(self):
        content = "Page 1 content\x0cPage 2 content\x0cPage 3 content"
        p = profile_document(content)
        assert p.form_feed_count == 2

    def test_language_detection_zh(self):
        p = profile_document("hair perm chemistry breaks disulfide bonds")
        assert "zh" in p.detected_langs or "en" in p.detected_langs

    def test_language_detection_mixed(self):
        p = profile_document("Hair perm uses chemical reactions 烫发原理")
        assert "zh" in p.detected_langs
        assert "en" in p.detected_langs

    def test_code_ratio(self):
        content = "preface\n```\nprint('x' * 100)\n```\nepilogue"
        p = profile_document(content)
        assert p.code_ratio > 0

    def test_profile_to_dict(self):
        p = profile_document("# title\nbody")
        d = p.to_dict()
        assert "total_chars" in d
        assert "recommended_tier" in d
        assert isinstance(d["md_heading_counts"], dict)


class TestSelectTier:
    def test_tier1_with_clear_h1_h2(self):
        p = DocProfile(md_heading_counts={1: 2, 2: 2}, total_chars=1000)
        assert select_tier(p) == 1

    def test_tier1_with_total_headings(self):
        p = DocProfile(md_heading_counts={3: 5}, total_chars=1000)
        assert select_tier(p) == 1

    def test_tier2_with_numbered_sections(self):
        p = DocProfile(md_heading_counts={}, numbered_section_count=5)
        assert select_tier(p) == 2

    def test_tier2_with_form_feeds(self):
        p = DocProfile(md_heading_counts={}, form_feed_count=3)
        assert select_tier(p) == 2

    def test_tier2_with_multi_lang(self):
        p = DocProfile(md_heading_counts={}, detected_langs=["zh", "en"])
        assert select_tier(p) == 2

    def test_tier3_fallback(self):
        p = DocProfile(md_heading_counts={}, detected_langs=["zh"])
        assert select_tier(p) == 3

    def test_explain_tier_choice(self):
        p = DocProfile(md_heading_counts={1: 5})
        explain = explain_tier_choice(p)
        assert "Tier 1" in explain


class TestProfileAndSelect:
    def test_md_doc_gets_tier1(self):
        content = (
            "# Perm Chemistry\n\n## Softening\n"
            "Apply thioglycolate.\n\n## Setting\n"
            "Set with bromate.\n\n## Notes\nFrequent perm damages cuticle.\n"
        )
        profile, tier = profile_and_select(content)
        assert tier == 1
        assert profile.recommended_tier == 1
        assert "Tier 1" in profile.recommended_reason

    def test_plain_text_gets_tier3(self):
        profile, tier = profile_and_select("plain text, no headings no tables no code")
        assert tier == 3

    def test_pdf_scanned_gets_tier2(self):
        content = "page 1 content\x0cpage 2 content\x0cpage 3 content"
        profile, tier = profile_and_select(content)
        assert tier == 2


class TestChunkWithTier:
    def test_tier1_uses_heading(self):
        content = (
            "# Ch1 Perm\n\n## Soften\nSoften is step 1.\n\n"
            "# Ch2 Dye\n\n## Pre-dye\nPre-dye allergy test.\n"
        )
        profile, tier = profile_and_select(content)
        chunks = chunk_with_tier(content, profile, tier, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 0
        assert any("Soften" in c for c in chunks)

    def test_tier2_with_form_feed(self):
        content = "page 1 content with some text to make it longer\x0cpage 2 content also long\x0cpage 3 content"
        profile, tier = profile_and_select(content)
        chunks = chunk_with_tier(content, profile, tier, chunk_size=30, chunk_overlap=5)
        assert len(chunks) > 0

    def test_tier3_recursive(self):
        content = "this is plain text without headings. " * 30
        profile, tier = profile_and_select(content)
        chunks = chunk_with_tier(content, profile, tier, chunk_size=100, chunk_overlap=20)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 200

    def test_protects_tables_in_tier1(self):
        content = (
            "# Product Table\n\n| dye | ingredient |\n| --- | --- |\n"
            "| A   | ammonia |\n| B   | peroxide |\n\n## Usage\nMix by ratio.\n"
        )
        profile, tier = profile_and_select(content)
        chunks = chunk_with_tier(content, profile, tier, chunk_size=500, chunk_overlap=20)
        assert any("ammonia" in c and "peroxide" in c for c in chunks)
