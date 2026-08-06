# -*- coding: utf-8 -*-
"""音频解析器 (Whisper ASR).

借鉴 ekbs audio_parser: 语音转文字 (ASR).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ParentChunk
from app.rag.parsers.utils import download_file

logger = logging.getLogger(__name__)


class AudioParser:
    SUPPORTED_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

    def __init__(self, file_uri, filename=""):
        self.file_uri = file_uri
        self.filename = filename

    def load(self, document_id="", tenant_id="default", category="audio"):
        """音频 -> 1 个 ParentChunk (ASR 转写)。"""
        text = self._transcribe()
        child = ChildChunk(content=text, chunk_type="audio", source=self.file_uri)
        parent = ParentChunk(
            document_id=document_id or self.filename,
            tenant_id=tenant_id,
            category=category,
            child_chunks=[child],
        )
        return [parent]

    def _transcribe(self):
        """用 SiliconFlow Whisper API 转写。"""
        import httpx
        path = download_file(self.file_uri)
        api_key = os.environ.get("TEXT_EMBEDDING_API_KEY", "")
        if not api_key:
            return f"[音频: {Path(self.file_uri).name} - 未配置 API key]"
        try:
            with open(path, "rb") as f:
                files = {"file": (Path(path).name, f, "audio/mpeg")}
                data = {"model": "whisper-1"}
                headers = {"Authorization": f"Bearer {api_key}"}
                r = httpx.post(
                    "https://api.siliconflow.cn/v1/audio/transcriptions",
                    files=files, data=data, headers=headers, timeout=120.0,
                )
                r.raise_for_status()
                return r.json().get("text", "").strip() or "[音频转写为空]"
        except Exception as e:
            logger.warning("音频 ASR 失败: %s", e)
            return f"[音频: {Path(self.file_uri).name} - 转写失败: {e}]"


__all__ = ["AudioParser"]
