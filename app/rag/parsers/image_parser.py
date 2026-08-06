# -*- coding: utf-8 -*-
"""图片解析器 (VLM OCR).

借鉴 ekbs image_parser: 用多模态 LLM 识别图片内容。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ParentChunk
from app.rag.parsers.utils import download_file

logger = logging.getLogger(__name__)


class ImageParser:
    SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

    def __init__(self, file_uri: str, filename: str = ""):
        self.file_uri = file_uri
        self.filename = filename

    def load(self, document_id: str = "", tenant_id: str = "default",
            category: str = "image", min_size: int = 100) -> List[ParentChunk]:
        """图片 -> 1 个 ParentChunk（含 1 个 ChildChunk = VLM 描述）。

        借鉴 ekbs: 用多模态 LLM 做 OCR + 描述。
        """
        import asyncio
        try:
            from app.embedding.router import get_model_router, Capability
            from app.core.model_factory import get_model
            from agentscope.message import TextBlock, UserMsg, DataBlock, Base64Source
            path = download_file(self.file_uri, min_size=min_size)
            with open(path, "rb") as f:
                img_bytes = f.read()
            ext = Path(path).suffix.lower().lstrip(".") or "jpeg"
            mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
            b64 = base64.b64encode(img_bytes).decode()
            sys_msg = UserMsg(name="system", content=[TextBlock(
                text="你是图片理解专家，描述这张图片的文字内容、关键信息和场景。"
            )])
            user_msg = UserMsg(name="user", content=[
                DataBlock(source=Base64Source(data=b64, media_type=mime)),
                TextBlock(text="请详细描述这张图片的内容。"),
            ])
            model = get_model("chat")
            resp = asyncio.run(model([sys_msg, user_msg], stream=False))
            text = ""
            if hasattr(resp, "content") and resp.content:
                for b in resp.content:
                    if hasattr(b, "text") and b.text:
                        text += b.text
            text = text.strip() or "[图片理解失败]"
        except Exception as e:
            logger.warning("图片 VLM 解析失败: %s", e)
            text = f"[图片: {Path(self.file_uri).name} - 解析失败: {e}]"

        child = ChildChunk(content=text, chunk_type="image", source=self.file_uri)
        parent = ParentChunk(
            document_id=document_id or self.filename,
            tenant_id=tenant_id,
            category=category,
            child_chunks=[child],
        )
        return [parent]


__all__ = ["ImageParser"]
