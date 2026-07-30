# -*- coding: utf-8 -*-
"""图片解析器（.jpg / .png / .gif / .bmp / .webp）。

长宽比过大的长图先按固定边长切成多段，逐段交视觉模型做 OCR 与内容描述，
再把描述汇聚成 Block。视觉模型不可用时，降级为仅保留图片地址的图片 Segment，
不影响主流程。
"""
from __future__ import annotations

import io
import logging
import os
import random
from datetime import datetime
from pathlib import Path

from .base import BaseParser
from .doc_types import Block, SegmentKind
from . import vlm

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    """图片解析器。"""

    MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 图片下载上限：50MB

    def __init__(
        self,
        file_uri: str,
        filename: str,
        max_ratio: float = 3.0,
        max_segment_length: int = 1500,
    ) -> None:
        """初始化。

        Args:
            file_uri: 图片本地路径或安全 URL。
            filename: 原始文件名。
            max_ratio: 触发切分的最小长宽比。
            max_segment_length: 每段的最大边长（像素）。
        """
        super().__init__(file_uri, filename)
        self.max_ratio = max_ratio
        self.max_segment_length = max_segment_length

    def load(self) -> list[Block]:
        """解析图片文件。"""
        tiles = self._tile_if_long()

        pieces: list[tuple] = []
        prev_tail = None
        for index, tile in enumerate(tiles):
            hint_parts = []
            if len(tiles) > 1:
                hint_parts.append(f"这是长图的第 {index + 1} 段")
            if prev_tail:
                hint_parts.append(f"上一段结尾：{prev_tail}")
            description = vlm.describe_image(tile, extra_hint="；".join(hint_parts))
            pieces.append((SegmentKind.IMAGE, description, tile))
            prev_tail = (description or "")[-100:] or None

        return self.build_blocks(pieces)

    # ------------------------------------------------------------------
    # 长图切分
    # ------------------------------------------------------------------

    def _tile_if_long(self) -> list[str]:
        """长图切成多段返回其路径；无需切分则返回单张。"""
        try:
            from PIL import Image
        except Exception:  # noqa: BLE001
            logger.warning("Pillow 未安装，跳过长图切分")
            return [self.file_path] if self.file_path else []

        source = io.BytesIO(self._read_binary()) if self.file_url else self.file_path
        image = Image.open(source)

        width, height = image.size
        fmt = image.format or "PNG"
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(random.randint(100, 999))
        work_dir = Path(os.getenv("TEMP", "/tmp")) / "hair_kb_parse"
        work_dir.mkdir(parents=True, exist_ok=True)

        limit = self.max_segment_length
        if width / height > self.max_ratio and width > limit:
            return self._cut(image, stamp, work_dir, fmt, horizontal=True)
        if height / width > self.max_ratio and height > limit:
            return self._cut(image, stamp, work_dir, fmt, horizontal=False)

        # 无需切分：本地图片直接复用路径，远程图片落盘一份
        if self.file_path:
            return [self.file_path]
        ext = ".jpg" if fmt.upper() in ("JPEG", "JPG") else f".{fmt.lower()}"
        saved = work_dir / f"{stamp}{ext}"
        image.save(saved, format=fmt)
        return [str(saved)]

    def _cut(self, image, stamp, work_dir, fmt, horizontal: bool) -> list[str]:
        """沿水平（horizontal=True 按宽）或垂直方向等分切图。"""
        width, height = image.size
        step = self.max_segment_length
        save_fmt = fmt if fmt in ("JPEG", "PNG", "GIF", "BMP") else "PNG"
        ext = ".jpg" if save_fmt in ("JPEG", "JPG") else f".{save_fmt.lower()}"

        span = width if horizontal else height
        count = (span + step - 1) // step

        paths: list[str] = []
        for k in range(count):
            lo, hi = k * step, min((k + 1) * step, span)
            box = (lo, 0, hi, height) if horizontal else (0, lo, width, hi)
            tile = image.crop(box)
            if save_fmt == "JPEG" and tile.mode in ("RGBA", "LA", "P"):
                tile = tile.convert("RGB")
            axis = "w" if horizontal else "h"
            path = work_dir / f"{stamp}_{axis}{k + 1:02d}{ext}"
            tile.save(path, format=save_fmt)
            paths.append(str(path))
        return paths
