# -*- coding: utf-8 -*-
"""RAG 3 层校验 + 多格式 routing 测试.

借鉴 ekbs 多文档格式 + JavaGuide data-validation.
"""
import pytest

from app.rag.parsers import (
    get_parser, is_supported, get_supported_extensions,
    MarkdownParser, PdfParser, DocxParser, ExcelParser,
    ImageParser, AudioParser, TxtParser,
)
from app.rag.quality.validator import (
    validate_document_level, validate_chunk_level, validate_answer_level,
    ValidationResult,
)


# ===================================================================
# 1. 格式支持 (routing)
# ===================================================================

class TestFormatRouting:
    def test_supported_extensions_count(self):
        exts = get_supported_extensions()
        assert len(exts) == 20  # 7 类文档 + 5 类图片 + 5 类音频 + 3 类文本

    def test_pdf_routes_to_pdf_parser(self):
        p = get_parser("test.pdf", "test.pdf")
        assert isinstance(p, PdfParser)

    def test_docx_routes_to_docx_parser(self):
        p = get_parser("test.docx", "test.docx")
        assert isinstance(p, DocxParser)

    def test_excel_routes_to_excel_parser(self):
        p = get_parser("test.xlsx", "test.xlsx")
        assert isinstance(p, ExcelParser)

    def test_md_routes_to_markdown(self):
        p = get_parser("test.md", "test.md")
        assert isinstance(p, MarkdownParser)

    def test_jpg_routes_to_image_parser(self):
        p = get_parser("test.jpg", "test.jpg")
        assert isinstance(p, ImageParser)

    def test_png_routes_to_image_parser(self):
        p = get_parser("test.png", "test.png")
        assert isinstance(p, ImageParser)

    def test_mp3_routes_to_audio_parser(self):
        p = get_parser("test.mp3", "test.mp3")
        assert isinstance(p, AudioParser)

    def test_txt_routes_to_txt_parser(self):
        p = get_parser("test.txt", "test.txt")
        assert isinstance(p, TxtParser)

    def test_fallback_to_txt(self):
        p = get_parser("test.xyz", "test.xyz")
        assert isinstance(p, TxtParser)

    def test_is_supported_positive(self):
        for f in ["a.pdf", "a.docx", "a.png", "a.mp3", "a.txt"]:
            assert is_supported(f), f"{f} should be supported"

    def test_is_supported_negative(self):
        for f in ["a.exe", "a.bat", "a.dll"]:
            assert not is_supported(f), f"{f} should not be supported"


# ===================================================================
# 2. 第 1 层: 文档级校验
# ===================================================================

class TestDocumentLevel:
    def test_valid_pdf(self):
        r = validate_document_level("manual.pdf", 1024 * 1024)
        assert r.passed
        assert r.layer == "document"

    def test_empty_filename(self):
        r = validate_document_level("", 1024)
        assert not r.passed
        assert "filename" in r.reason

    def test_empty_file(self):
        r = validate_document_level("a.pdf", 0)
        assert not r.passed

    def test_too_small(self):
        r = validate_document_level("a.pdf", 50)  # < 100 字节
        assert not r.passed
        assert "too small" in r.reason.lower()

    def test_too_large(self):
        r = validate_document_level("a.pdf", 200 * 1024 * 1024)  # 200MB
        assert not r.passed
        assert "too large" in r.reason.lower()

    def test_unsupported_format(self):
        r = validate_document_level("virus.exe", 1024)
        assert not r.passed
        assert "unsupported" in r.reason.lower()

    def test_image_format(self):
        r = validate_document_level("photo.jpg", 5000)
        assert r.passed

    def test_audio_format(self):
        r = validate_document_level("voice.mp3", 50000)
        assert r.passed


# ===================================================================
# 3. 第 2 层: 块级校验
# ===================================================================

class TestChunkLevel:
    def test_valid_chunk(self):
        r = validate_chunk_level("This is a normal chunk with enough text to pass validation.")
        assert r.passed

    def test_empty_chunk(self):
        r = validate_chunk_level("")
        assert not r.passed

    def test_too_short(self):
        r = validate_chunk_level("short")
        assert not r.passed
        assert "too short" in r.reason.lower()

    def test_too_long(self):
        r = validate_chunk_level("x" * 6000)
        assert not r.passed
        assert "too long" in r.reason.lower()

    def test_high_duplicate(self):
        # Same line repeated 10 times
        text = "\n".join(["same line"] * 10)
        r = validate_chunk_level(text)
        assert not r.passed
        assert "duplicate" in r.reason.lower()


    def test_embedding_empty(self):
        r = validate_chunk_level("valid content here", [])
        assert not r.passed


# ===================================================================
# 4. 第 3 层: 答案级校验
# ===================================================================

class TestAnswerLevel:
    def test_no_hits_warning(self):
        r = validate_answer_level([])
        assert not r.passed
        assert "no retrieval" in r.reason.lower()

    def test_low_avg_similarity(self):
        class Hit:
            def __init__(self, s): self.score = s
        r = validate_answer_level([Hit(0.1), Hit(0.2), Hit(0.15)])
        assert not r.passed

    def test_low_top1(self):
        class Hit:
            def __init__(self, s): self.score = s
        r = validate_answer_level([Hit(0.2), Hit(0.3), Hit(0.4)])
        # top1 = 0.4 < 阈值 0.4 不严格通过
        # (边界值: top1=0.4 == MIN_TOP1_SIMILARITY=0.4, 通过)
        # 实际: 0.4 = 阈值, 通过. 改 0.35
        r = validate_answer_level([Hit(0.2), Hit(0.25), Hit(0.35)])
        assert not r.passed

    def test_valid_answer(self):
        class Hit:
            def __init__(self, s): self.score = s
        r = validate_answer_level(
            [Hit(0.8), Hit(0.7), Hit(0.6)],
            llm_answer="This is a comprehensive answer with details."
        )
        assert r.passed

    def test_short_answer_warning(self):
        class Hit:
            def __init__(self, s): self.score = s
        r = validate_answer_level([Hit(0.8)], llm_answer="hi")
        assert not r.passed
