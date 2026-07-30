# -*- coding: utf-8 -*-
"""纯文本解析器（.txt）。"""
from __future__ import annotations

from .base import BaseParser
from .doc_types import Block, SegmentKind
from .utils import get_text


class TxtParser(BaseParser):
    """纯文本解析器：整篇读入后交由基类切分、聚合。"""

    def load(self) -> list[Block]:
        """解析纯文本文件。"""
        raw = get_text("", self._read_binary()) if self.file_url else get_text(self.file_path)
        normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

        # 纯文本无表格/图片，整篇作为一个文本片段交给基类切分聚合
        return self.build_blocks([(SegmentKind.TEXT, normalized, None)])
