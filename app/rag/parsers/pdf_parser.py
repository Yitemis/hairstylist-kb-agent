# -*- coding: utf-8 -*-
"""PDF 解析器（PyMuPDF + MinerU 双引擎，借鉴九阳 POC 实战经验）。

借鉴思路：横版 + OCR 兜底（来自九阳 POC 失分最多场景）。
两个引擎：
- MinerU (Apache 2.0, 完全开源免费)：专用 layout 分析，多栏/表格/公式 SOTA
- PyMuPDF (Apache 2.0, 完全开源免费)：标准文本提取，速度极快

回退策略：MinerU 失败 → 自动降级 PyMuPDF
"""
from __future__ import annotations

import logging
import os
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ElementType, ParentChunk
from app.rag.parsers.utils import download_file, is_safe_url

# 顶层不 import smart_chunker（避免循环 import 触发 partial-init）
# 全部改为函数内 lazy import

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB


class PdfParser:
    """PDF 文档解析器（PyMuPDF + MinerU 双引擎）。

    选择策略：
    1. 优先 MinerU（识别率高，支持 layout）
    2. MinerU 不可用/失败 → PyMuPDF
    3. PyMuPDF 也失败 → OCR 兜底
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
        binary = self._read_file()

        # 策略（借鉴九阳 POC）：所有 PDF 默认走 MinerU（layout 分析 + Markdown 输出）
        # 失败/不可用时降级到 PyMuPDF
        # 环境变量 PDF_PARSER：
        #   auto (默认)：MinerU 优先，失败降级 PyMuPDF
        #   mineru：强制要求 MinerU，失败报错（生产用）
        #   fast / pymupdf：只用 PyMuPDF（快，0 依赖，仅适合纯文本）
        parser_choice = os.environ.get("PDF_PARSER", "auto").lower()
        pages_text: List[str] = []
        if parser_choice in ("mineru", "auto"):
            pages_text = self._extract_with_mineru(binary)
            if not pages_text and parser_choice == "mineru":
                logger.warning("MinerU 不可用，强制要求 MinerU 模式（不降级）")
            elif not pages_text and parser_choice == "auto":
                logger.info("MinerU 不可用，降级到 PyMuPDF")
                pages_text = self._extract_with_pymupdf(binary)
        elif parser_choice in ("pymupdf", "fast"):
            pages_text = self._extract_with_pymupdf(binary)
        else:
            logger.warning(f"未知 PDF_PARSER={parser_choice}，用 MinerU")
            pages_text = self._extract_with_mineru(binary) or self._extract_with_pymupdf(binary)

        if not pages_text:
            logger.error("PDF 解析完全失败（两个引擎都不可用）")
            return []

        full_text = "\n\n".join(pages_text)
        # Lazy import to avoid circular dependency
        from app.rag.chunkers.smart_chunker import (
            build_child_chunks, build_parent_chunks,
            extract_qa_pairs, merge_qa_into_chunks, split_markdown_by_heading,
        )
        sections = split_markdown_by_heading(full_text, chunk_size, chunk_overlap)
        qa_pairs = extract_qa_pairs(full_text)
        if qa_pairs:
            sections = merge_qa_into_chunks(sections, qa_pairs)

        child_chunks = build_child_chunks(
            sections, source_filename=self.filename, document_id=document_id,
            tenant_id=tenant_id, category=category,
        )
        return build_parent_chunks(
            child_chunks, parent_chunk_size=parent_chunk_size,
            source_filename=self.filename, document_id=document_id, tenant_id=tenant_id,
        )

    def _extract_with_mineru(self, binary: bytes) -> List[str]:
        """用 MinerU 后端解析（支持 3 种后端，自动降级）。

        后端选择（环境变量 MINERU_BACKEND，默认 local）:
            - local (默认): 本地 pipeline，CPU，准确率 86.47
                           需 pip install -U "mineru[all]"
            - cloud       : mineru.net 官方云 API，每天 1000 页免费
                           需 MINERU_API_TOKEN 环境变量
            - http        : OpenAI 兼容 API（自建或第三方）
                           需 MINERU_HTTP_URL 环境变量

        失败自动降级由 PdfParser 统一调度（→ PyMuPDF → pdfplumber → OCR）
        """
        from app.rag.parsers.mineru_backends import get_mineru_backend
        backend = get_mineru_backend()
        return backend.parse(binary, self.filename)

    def _extract_with_pymupdf(self, binary: bytes) -> List[str]:
        """PyMuPDF 提取（降级路径，0 成本，Apache 2.0 开源）。"""
        try:
            import fitz
            import io
            doc = fitz.open(stream=io.BytesIO(binary))
            pages_text = []
            for page in doc:
                if page.rect.width > page.rect.height:
                    page.set_rotation(90)
                text = page.get_text("text")
                if not text.strip():
                    text = self._ocr_page_fitz(page)
                pages_text.append(text)
            doc.close()
            return pages_text
        except ImportError:
            return self._extract_with_pdfplumber(binary)

    def _extract_with_pdfplumber(self, binary: bytes) -> List[str]:
        """pdfplumber 提取（最后降级，MIT 开源）。"""
        try:
            import pdfplumber
            import io
            pages_text = []
            with pdfplumber.open(io.BytesIO(binary)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if not text.strip():
                        text = self._ocr_page_pdfplumber(page)
                    pages_text.append(text)
            return pages_text
        except ImportError:
            return []

    def _ocr_page_fitz(self, page) -> str:
        """OCR 兜底（横版扫描件）。"""
        try:
            import pytesseract
            from PIL import Image
            import io
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img, lang="chi_sim+eng")
        except Exception as e:
            logger.warning(f"OCR 失败: {e}")
            return ""

    def _ocr_page_pdfplumber(self, page) -> str:
        try:
            import pytesseract
            img = page.to_image(resolution=200).original
            return pytesseract.image_to_string(img, lang="chi_sim+eng")
        except Exception:
            return ""

    def _read_file(self) -> bytes:
        if self.file_url:
            return download_file(self.file_url, MAX_FILE_SIZE)
        with open(self.file_path, "rb") as f:
            return f.read()
