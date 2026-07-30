# -*- coding: utf-8 -*-
"""Word 解析器（.docx）。

基于 python-docx 按文档流顺序遍历段落、表格与内嵌图片：

- 段落：作为文本片段，标题转成 ``#`` 前缀以便按层级聚合；
- 表格：转 HTML 后交模型结构化；
- 内嵌图片：抽出二进制交模型描述。

相关模型不可用时自动降级，不影响主流程。
"""
from __future__ import annotations

import base64
import logging

from .base import BaseParser
from .doc_types import Block, SegmentKind
from . import vlm

logger = logging.getLogger(__name__)


class DocxParser(BaseParser):
    """Word 文档解析器。"""

    def load(self) -> list[Block]:
        """解析 .docx 文件。"""
        from io import BytesIO

        import docx

        document = docx.Document(BytesIO(self._read_binary()))

        pieces: list[tuple] = []
        for kind, item in self._walk(document):
            if kind == "paragraph":
                pieces.extend(self._paragraph_pieces(item, document))
            else:  # table
                table_html = self._table_to_html(item)
                structured = vlm.structure_table(table_html)
                pieces.append((SegmentKind.TABLE, structured, table_html))

        return self.build_blocks(pieces)

    def _paragraph_pieces(self, para, document) -> list[tuple]:
        """把一个段落展开为文本 + 内嵌图片片段。"""
        result: list[tuple] = []

        text = para.text.strip()
        if text:
            style = (para.style.name or "").lower()
            if style.startswith("heading"):
                digits = "".join(c for c in style if c.isdigit()) or "1"
                text = "#" * int(digits) + " " + text
            result.append((SegmentKind.TEXT, text, None))

        for description, ref in self._paragraph_images(para, document):
            result.append((SegmentKind.IMAGE, description, ref))
        return result

    # ------------------------------------------------------------------
    # 文档流遍历（保持段落与表格的原始先后顺序）
    # ------------------------------------------------------------------

    @staticmethod
    def _walk(document):
        """顺序产出 ('paragraph', Paragraph) / ('table', Table)。"""
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        for element in document.element.body.iterchildren():
            if isinstance(element, CT_P):
                yield "paragraph", Paragraph(element, document)
            elif isinstance(element, CT_Tbl):
                yield "table", Table(element, document)

    @staticmethod
    def _table_to_html(table) -> str:
        """把 docx 表格渲染为 HTML。

        python-docx 对合并单元格会在多个网格位置返回同一 cell 对象并携带相同
        文本，因此逐行读取 ``row.cells`` 即已把合并值填充到每个网格位，列对齐
        自然保持。统一交给表格工具渲染，与 Excel 输出结构一致。
        """
        from . import tables

        grid = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        return tables.matrix_to_html(grid) if grid else "<table></table>"

    _NS_DRAWING = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    _NS_EMBED = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    )

    @classmethod
    def _paragraph_images(cls, para, document):
        """抽取段落内嵌图片，逐张交模型描述，产出 (描述, data_url)。"""
        output = []
        for blip in para._p.findall(f".//{cls._NS_DRAWING}"):
            rel_id = blip.get(cls._NS_EMBED)
            if not rel_id:
                continue
            try:
                part = document.part.related_parts[rel_id]
                mime = part.content_type or "image/png"
                encoded = base64.b64encode(part.blob).decode()
                data_url = f"data:{mime};base64,{encoded}"
                output.append((vlm.describe_image(data_url), data_url))
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 docx 内嵌图片失败: %s", exc)
        return output
