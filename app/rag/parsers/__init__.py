# -*- coding: utf-8 -*-
"""文档解析器统一调度。"""
from app.rag.parsers.markdown_parser import MarkdownParser
from app.rag.parsers.pdf_parser import PdfParser
from app.rag.parsers.docx_parser import DocxParser
from app.rag.parsers.excel_parser import ExcelParser


def get_parser(file_uri: str, filename: str):
    """按文件扩展名返回对应解析器。"""
    name = (filename or file_uri or "").lower()
    if name.endswith(".md") or name.endswith(".markdown"):
        return MarkdownParser(file_uri, filename)
    if name.endswith(".pdf"):
        return PdfParser(file_uri, filename)
    if name.endswith(".docx") or name.endswith(".doc"):
        return DocxParser(file_uri, filename)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return ExcelParser(file_uri, filename)
    # fallback：尝试当 markdown
    return MarkdownParser(file_uri, filename)


__all__ = ["MarkdownParser", "PdfParser", "DocxParser", "ExcelParser", "get_parser"]
