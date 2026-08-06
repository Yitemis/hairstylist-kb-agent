# -*- coding: utf-8 -*-
"""文档解析器统一调度 (借鉴 ekbs multi-format routing).

支持的格式 (7 类 19 种):
- PDF (MinerU)
- Word (.docx/.doc)
- Excel (.xlsx/.xls)
- Markdown (.md/.markdown)
- Image (.jpg/.jpeg/.png/.webp/.bmp) - VLM OCR
- Audio (.mp3/.wav/.m4a/.ogg/.flac) - Whisper ASR
- Text (.txt/.log/.rst) - 自动编码检测
"""
from app.rag.parsers.markdown_parser import MarkdownParser
from app.rag.parsers.pdf_parser import PdfParser
from app.rag.parsers.docx_parser import DocxParser
from app.rag.parsers.excel_parser import ExcelParser
from app.rag.parsers.image_parser import ImageParser
from app.rag.parsers.audio_parser import AudioParser
from app.rag.parsers.txt_parser import TxtParser

ALL_SUPPORTED_EXTS = (
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".md", ".markdown",
    ".jpg", ".jpeg", ".png", ".webp", ".bmp",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".txt", ".log", ".rst",
)


def get_parser(file_uri, filename=""):
    """按文件扩展名返回对应解析器 (借鉴 ekbs routing)."""
    name = (filename or file_uri or "").lower()
    if name.endswith(".pdf"):
        return PdfParser(file_uri, filename)
    if name.endswith(".docx") or name.endswith(".doc"):
        return DocxParser(file_uri, filename)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return ExcelParser(file_uri, filename)
    if name.endswith(".md") or name.endswith(".markdown"):
        return MarkdownParser(file_uri, filename)
    if any(name.endswith(ext) for ext in ImageParser.SUPPORTED_EXTS):
        return ImageParser(file_uri, filename)
    if any(name.endswith(ext) for ext in AudioParser.SUPPORTED_EXTS):
        return AudioParser(file_uri, filename)
    if any(name.endswith(ext) for ext in TxtParser.SUPPORTED_EXTS):
        return TxtParser(file_uri, filename)
    return TxtParser(file_uri, filename)


def is_supported(filename):
    return any((filename or "").lower().endswith(ext) for ext in ALL_SUPPORTED_EXTS)


def get_supported_extensions():
    return list(ALL_SUPPORTED_EXTS)


__all__ = [
    "MarkdownParser", "PdfParser", "DocxParser", "ExcelParser",
    "ImageParser", "AudioParser", "TxtParser",
    "get_parser", "is_supported", "get_supported_extensions",
]
