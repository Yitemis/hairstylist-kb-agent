# -*- coding: utf-8 -*-
"""TXT 解析器 - 自动检测编码 (借鉴 ekbs).

支持 utf-8 / utf-8-sig / gbk / gb18030 / latin-1 / big5.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ParentChunk
from app.rag.parsers.utils import download_file

logger = logging.getLogger(__name__)


# 借鉴 ekbs + chardet
ENCODINGS_TRY = ["utf-8", "utf-8-sig", "gbk", "gb18030", "big5", "latin-1"]


def _detect_and_read(path: str) -> str:
    """自动检测编码读取文件。"""
    # 优先用 chardet
    try:
        import chardet
        with open(path, "rb") as f:
            raw = f.read()
        detected = chardet.detect(raw)
        enc = detected.get("encoding") or "utf-8"
        if enc.lower().startswith("gb"):
            enc = "gbk"  # 兼容
        return raw.decode(enc, errors="replace")
    except ImportError:
        pass
    # 降级：逐个试
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ENCODINGS_TRY:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class TxtParser:
    SUPPORTED_EXTS = (".txt", ".log", ".md", ".rst")

    def __init__(self, file_uri: str, filename: str = ""):
        self.file_uri = file_uri
        self.filename = filename

    def load(self, document_id: str = "", tenant_id: str = "default",
            category: str = "text", max_chunk: int = 2000) -> List[ParentChunk]:
        """TXT -> 多个 ParentChunk (按段切分)。"""
        path = download_file(self.file_uri)
        text = _detect_and_read(path)
        # 按空行分段
        sections = [s.strip() for s in text.split("\n\n") if s.strip()]
        if not sections:
            sections = [text]
        parents = []
        for i, sec in enumerate(sections[:max_chunk]):
            child = ChildChunk(content=sec, chunk_type="text", source=self.file_uri)
            parent = ParentChunk(
                document_id=document_id or self.filename,
                tenant_id=tenant_id,
                category=category,
                child_chunks=[child],
            )
            parents.append(parent)
        return parents


__all__ = ["TxtParser"]
