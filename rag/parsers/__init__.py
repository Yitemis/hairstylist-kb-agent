# -*- coding: utf-8 -*-
"""多模态文档解析模块。

统一入口 :func:`parse_document`：按扩展名分发到对应解析器，产出
``list[Block]`` 两层结构（Block 提供上下文、Segment 提供检索粒度），供 RAG
引擎索引。

支持格式：
    - .txt              纯文本
    - .md / .markdown   Markdown（含表格 / 图片 / 代码块）
    - .docx             Word（段落 / 表格 / 内嵌图片）
    - .xlsx / .xls      Excel（多工作表 -> 表格结构化）
    - .pdf              PDF（MinerU 优先，本地 PyMuPDF 降级）
    - 图片格式          jpg/png/gif/bmp/webp（长图切分 + 视觉模型描述）

设计原则：
    1. 所有解析器统一产出 Block / Segment 两层结构；
    2. 表格与图片交由模型语义化，相关依赖缺失时优雅降级；
    3. 解析器可单独实例化，也可通过工厂按扩展名自动选择。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseParser
from .doc_types import Block, Segment, SegmentKind
from .docx_parser import DocxParser
from .excel_parser import ExcelParser
from .image_parser import ImageParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .txt_parser import TxtParser

logger = logging.getLogger(__name__)


# 扩展名 -> 解析器类
_PARSER_BY_EXT: dict[str, type[BaseParser]] = {
    ".txt": TxtParser,
    ".md": MarkdownParser,
    ".markdown": MarkdownParser,
    ".docx": DocxParser,
    ".xlsx": ExcelParser,
    ".xls": ExcelParser,
    ".pdf": PdfParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".png": ImageParser,
    ".gif": ImageParser,
    ".bmp": ImageParser,
    ".webp": ImageParser,
}

SUPPORTED_EXTS = tuple(_PARSER_BY_EXT.keys())


def get_parser_class(ext: str) -> type[BaseParser] | None:
    """按扩展名返回解析器类。"""
    return _PARSER_BY_EXT.get(ext.lower())


def parse_document(
    file_uri: str,
    filename: str | None = None,
) -> list[Block]:
    """解析文档，按扩展名自动选择解析器。

    Args:
        file_uri: 文件本地路径或安全的 http(s) URL。
        filename: 原始文件名（用于确定扩展名与溯源）；缺省时从 file_uri 推断。

    Returns:
        list[Block]: 解析出的 Block 列表。

    Raises:
        ValueError: 扩展名不受支持时。
    """
    name = filename or Path(file_uri).name
    ext = Path(name).suffix.lower()

    parser_cls = get_parser_class(ext)
    if parser_cls is None:
        raise ValueError(f"暂不支持的文件格式: {ext}（来源: {name}）")

    logger.info("使用 %s 解析 %s", parser_cls.__name__, name)
    parser = parser_cls(file_uri=file_uri, filename=name)
    return parser.load()


__all__ = [
    "parse_document",
    "get_parser_class",
    "SUPPORTED_EXTS",
    "BaseParser",
    "Block",
    "Segment",
    "SegmentKind",
    "TxtParser",
    "MarkdownParser",
    "DocxParser",
    "ExcelParser",
    "PdfParser",
    "ImageParser",
]
