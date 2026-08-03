# -*- coding: utf-8 -*-
"""Markdown 解析器。

基于 Python markdown 标准库 + BeautifulSoup。
借鉴思路：按 ## 标题层级切分（来自九阳 POC 实战）。
"""
from __future__ import annotations

import re
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ElementType, ParentChunk
from app.rag.parsers.utils import detect_encoding, download_file, is_safe_url
from app.rag.chunkers.smart_chunker import (
    build_child_chunks,
    build_parent_chunks,
    extract_qa_pairs,
    merge_qa_into_chunks,
    split_markdown_by_heading,
)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class MarkdownParser:
    """Markdown 文档解析器。

    Pipeline:
    1. 读取文件（支持 URL 和本地路径，含 SSRF 防护）
    2. 按 ## 标题层级切分（800 字符 + 80 重叠）
    3. 提取 Q&A 速答段（追加到所有 chunk 末尾做冗余编码）
    4. 合并成父子分块
    """

    def __init__(self, file_uri: str, filename: str):
        if is_safe_url(file_uri):
            self.file_url = file_uri
            self.file_path = None
        else:
            self.file_path = file_uri
            self.file_url = None
        self.filename = filename

    def load(
        self,
        document_id: str = "",
        tenant_id: str = "default",
        category: str = "general",
        chunk_size: int = 800,
        chunk_overlap: int = 80,
        parent_chunk_size: int = 2000,
    ) -> List[ParentChunk]:
        text = self._read_file()
        sections = split_markdown_by_heading(text, chunk_size, chunk_overlap)
        qa_pairs = extract_qa_pairs(text)
        if qa_pairs:
            sections = merge_qa_into_chunks(sections, qa_pairs)
        child_chunks = build_child_chunks(
            sections,
            source_filename=self.filename,
            document_id=document_id,
            tenant_id=tenant_id,
            category=category,
        )
        return build_parent_chunks(
            child_chunks,
            parent_chunk_size=parent_chunk_size,
            source_filename=self.filename,
            document_id=document_id,
            tenant_id=tenant_id,
        )

    def _read_file(self) -> str:
        if self.file_url:
            content = download_file(self.file_url, MAX_FILE_SIZE)
            encoding = detect_encoding(content)
            return content.decode(encoding, errors="ignore")
        with open(self.file_path, "rb") as f:
            content = f.read()
        encoding = detect_encoding(content)
        return content.decode(encoding, errors="ignore")
