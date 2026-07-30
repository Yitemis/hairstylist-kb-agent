# -*- coding: utf-8 -*-
"""PDF 解析器（.pdf）。

两条解析路径，按可用性自动择优：

1. MinerU：配置 MINERU_URL 时调用 MinerU 服务做版面解析，还原文字、表格、
   图片、公式的阅读顺序，图片与表格再交模型理解；
2. 本地解析：未配置 MinerU 时用 PyMuPDF 逐页提取文字与内嵌图片，图片交视觉
   模型描述；PyMuPDF 不可用时退回 pypdf 纯文本。
"""
from __future__ import annotations

import base64
import json
import logging
import os

from .base import BaseParser
from .doc_types import Block, SegmentKind
from . import vlm

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """PDF 解析器。"""

    MAX_DOWNLOAD_SIZE = 200 * 1024 * 1024  # PDF 下载上限：200MB

    def load(self) -> list[Block]:
        """解析 PDF 文件。"""
        mineru_url = os.getenv("MINERU_URL", "").strip()
        if mineru_url:
            try:
                pieces = self._via_mineru(mineru_url)
                if pieces:
                    return self.build_blocks(pieces)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MinerU 解析失败，改用本地解析: %s", exc)

        return self.build_blocks(self._via_local())

    # ------------------------------------------------------------------
    # 路径 1：MinerU 服务
    # ------------------------------------------------------------------

    def _via_mineru(self, mineru_url: str) -> list[tuple]:
        """调用 MinerU /file_parse 接口，返回解析片段。"""
        import requests
        from io import BytesIO

        endpoint = mineru_url.rstrip("/") + "/file_parse"
        params = {
            "backend": os.getenv("MINERU_BACKEND", "pipeline"),
            "parse_method": os.getenv("MINERU_PARSE_METHOD", "auto"),
            "return_content_list": True,
            "return_images": True,
            "remove_temp_dir": True,
        }

        if self.file_url:
            payload = {"files": (self.filename, BytesIO(self._read_binary()), "application/pdf")}
            resp = requests.post(endpoint, files=payload, data=params, timeout=300)
        else:
            with open(self.file_path, "rb") as handle:
                resp = requests.post(
                    endpoint, files={"files": handle}, data=params, timeout=300,
                )
        resp.raise_for_status()

        pieces: list[tuple] = []
        for _name, result in resp.json().get("results", {}).items():
            items = json.loads(result["content_list"])
            image_pool = result.get("images", {})
            for item in items:
                pieces.append(self._mineru_item_to_piece(item, image_pool))

        return [p for p in pieces if p is not None]

    def _mineru_item_to_piece(self, item: dict, image_pool: dict) -> tuple | None:
        """把单个 MinerU 内容项转成解析片段。"""
        kind = item.get("type")

        if kind == "text":
            text = item.get("text", "")
            level = item.get("text_level")
            if level:
                text = "#" * int(level) + " " + text
            return (SegmentKind.TEXT, text, None)

        if kind == "equation":
            return (SegmentKind.TEXT, item.get("text", ""), None)

        if kind == "table":
            table_html = item.get("table_body", "")
            return (SegmentKind.TABLE, vlm.structure_table(table_html), table_html)

        if kind == "image":
            ref = item.get("img_path", "")
            encoded = image_pool.get(ref.split("/")[-1])
            caption = "\n".join(item.get("img_caption", []))
            description = None
            if encoded:
                description = vlm.describe_image(
                    f"data:image/png;base64,{encoded}", extra_hint=caption,
                )
            return (SegmentKind.IMAGE, description, ref)

        return None

    # ------------------------------------------------------------------
    # 路径 2：本地解析
    # ------------------------------------------------------------------

    def _via_local(self) -> list[tuple]:
        """本地解析：优先 PyMuPDF（文字+图片），失败退回 pypdf。"""
        try:
            return self._via_pymupdf()
        except Exception as exc:  # noqa: BLE001
            logger.warning("PyMuPDF 不可用，退回 pypdf 纯文本: %s", exc)
        return self._via_pypdf()

    def _via_pymupdf(self) -> list[tuple]:
        """PyMuPDF 逐页提取文字与内嵌图片。"""
        import fitz  # PyMuPDF

        document = (
            fitz.open(stream=self._read_binary(), filetype="pdf")
            if self.file_url else fitz.open(self.file_path)
        )

        pieces: list[tuple] = []
        for page in document:
            text = page.get_text("text").strip()
            if text:
                pieces.append((SegmentKind.TEXT, text, None))

            for image_meta in page.get_images(full=True):
                try:
                    xref = image_meta[0]
                    extracted = document.extract_image(xref)
                    encoded = base64.b64encode(extracted["image"]).decode()
                    ext = extracted.get("ext", "png")
                    description = vlm.describe_image(f"data:image/{ext};base64,{encoded}")
                    pieces.append((SegmentKind.IMAGE, description, f"page_img_{xref}"))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("PyMuPDF 图片抽取失败: %s", exc)
        document.close()
        return pieces

    def _via_pypdf(self) -> list[tuple]:
        """pypdf 纯文本兜底。"""
        from io import BytesIO

        from pypdf import PdfReader

        reader = (
            PdfReader(BytesIO(self._read_binary()))
            if self.file_url else PdfReader(self.file_path)
        )

        pieces: list[tuple] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pieces.append((SegmentKind.TEXT, text, None))
        return pieces
