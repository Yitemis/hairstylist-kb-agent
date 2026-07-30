# -*- coding: utf-8 -*-
"""解析器基类与通用切分/聚合算法。

各格式解析器继承 :class:`BaseParser` 并实现 :meth:`load`，最终都返回
``list[Block]``。基类提供两个跨格式复用的能力：

* :meth:`slice_segments` —— 把一段长文本切成若干 :class:`Segment`；
* :meth:`build_blocks`   —— 把有序的解析片段汇聚成 :class:`Block`。

约定的中间表示 ``Piece``：解析器先把文档还原成一串 ``Piece``，再交给
:meth:`build_blocks` 统一成块。每个 ``Piece`` 是三元组
``(kind, text, extra)``：

* ``kind``  —— :class:`SegmentKind`；
* ``text``  —— 文本；表格为空、图片为其描述；
* ``extra`` —— 表格传 HTML 原文，图片传媒体地址，文本传 ``None``。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .doc_types import Block, Segment, SegmentKind
from .utils import download_file, is_safe_url
from .utils import num_tokens_from_string as count_tokens

logger = logging.getLogger(__name__)


# 切分粒度：块面向上下文（约 512 token），段面向检索（约 128 token）
BLOCK_TOKEN_BUDGET = 512
SEGMENT_TOKEN_BUDGET = 128

# 句子边界字符。命中其一即可作为一个安全的切分点。
BOUNDARY_CHARS = frozenset("\n。！？!?；;")


class BaseParser:
    """所有格式解析器的基类。"""

    MAX_DOWNLOAD_SIZE = 20 * 1024 * 1024  # 远程文件下载上限：20MB

    def __init__(self, file_uri: str, filename: str) -> None:
        """初始化。

        Args:
            file_uri: 文件来源，本地路径或安全的 http(s) URL。
            filename: 原始文件名，用于结果溯源。
        """
        if not file_uri:
            raise ValueError("file_uri 为空")

        # 安全 URL 走下载，否则按本地路径处理
        if is_safe_url(file_uri):
            self.file_path = None
            self.file_url = file_uri
        else:
            self.file_path = file_uri
            self.file_url = None
        self.filename = filename

    def load(self) -> list[Block]:
        """解析文件并返回 Block 列表。子类必须覆写。"""
        raise NotImplementedError

    def _read_binary(self) -> bytes:
        """读取文件二进制（本地读盘或远程下载）。"""
        if self.file_url:
            return download_file(self.file_url, self.MAX_DOWNLOAD_SIZE)
        return Path(self.file_path).read_bytes()

    # ------------------------------------------------------------------
    # 文本 -> Segment：在句子边界处贪心累积到 token 预算
    # ------------------------------------------------------------------

    @staticmethod
    def slice_segments(
        text: str,
        token_budget: int = SEGMENT_TOKEN_BUDGET,
    ) -> list[Segment]:
        """把一段文本切成若干文本 Segment。

        算法：先在句子边界（换行、中英文句末标点）处把文本切成"句片"，
        再从前往后贪心地把句片拼进当前 Segment；一旦继续拼接会超出
        ``token_budget``，就结束当前 Segment 另起一个。单个句片自身即超预算时
        独立成段（不再强行二次切分，避免破坏句子完整性）。

        Args:
            text: 待切分文本。
            token_budget: 单个 Segment 的 token 上限。

        Returns:
            文本 Segment 列表，保持原文顺序。
        """
        if not text:
            return []

        pieces = BaseParser._split_on_boundaries(text)

        segments: list[Segment] = []
        buffer: list[str] = []
        buffer_tokens = 0

        def flush() -> None:
            nonlocal buffer, buffer_tokens
            if buffer:
                joined = "".join(buffer)
                segments.append(
                    Segment(text=joined, kind=SegmentKind.TEXT,
                            tokens=count_tokens(joined)),
                )
                buffer = []
                buffer_tokens = 0

        for piece in pieces:
            piece_tokens = count_tokens(piece)
            # 当前缓冲非空且再加这一片会超预算 -> 先落袋
            if buffer and buffer_tokens + piece_tokens > token_budget:
                flush()
            buffer.append(piece)
            buffer_tokens += piece_tokens

        flush()
        return segments

    @staticmethod
    def _split_on_boundaries(text: str) -> list[str]:
        """按句子边界切分，切分符归到其所在句片末尾。"""
        pieces: list[str] = []
        start = 0
        for idx, ch in enumerate(text):
            if ch in BOUNDARY_CHARS:
                pieces.append(text[start: idx + 1])
                start = idx + 1
        if start < len(text):
            pieces.append(text[start:])
        return pieces

    # ------------------------------------------------------------------
    # 解析片段 (Piece) -> Segment -> Block
    # ------------------------------------------------------------------

    @classmethod
    def build_blocks(
        cls,
        pieces: list[tuple],
        block_budget: int = BLOCK_TOKEN_BUDGET,
        segment_budget: int = SEGMENT_TOKEN_BUDGET,
    ) -> list[Block]:
        """把解析片段汇聚成 Block。

        先把每个 ``Piece`` 展开为一个或多个 Segment（长文本会被
        :meth:`slice_segments` 拆成多段），再顺序打包成 Block。

        Args:
            pieces: ``(kind, text, extra)`` 三元组列表，见模块文档。
            block_budget: 单个 Block 的 token 上限。
            segment_budget: 单个文本 Segment 的 token 上限。

        Returns:
            Block 列表。
        """
        segments: list[Segment] = []
        # 维护标题层级路径：以 '#' 前缀的文本片段视为标题，更新章节路径，
        # 后续片段继承当前路径，实现跨格式（docx/pdf/txt）的章节归属。
        heading_stack: list[str] = []

        for kind, text, extra in pieces:
            if kind == SegmentKind.TEXT:
                if not text:
                    continue
                level, title = cls._heading_of(text)
                if level:
                    heading_stack = heading_stack[: level - 1]
                    while len(heading_stack) < level - 1:
                        heading_stack.append("")
                    heading_stack.append(title)
                    section = [h for h in heading_stack[:-1] if h]
                else:
                    section = [h for h in heading_stack if h]

                for seg in cls.slice_segments(text, segment_budget):
                    seg.section = list(section)
                    segments.append(seg)
            elif kind == SegmentKind.TABLE:
                seg = cls._make_table_segment(text, extra)
                seg.section = [h for h in heading_stack if h]
                segments.append(seg)
            elif kind == SegmentKind.IMAGE:
                seg = cls._make_image_segment(text, extra)
                seg.section = [h for h in heading_stack if h]
                segments.append(seg)

        return cls.pack_blocks(segments, block_budget)

    @staticmethod
    def _heading_of(text: str) -> tuple[int, str]:
        """识别 '#' 前缀标题，返回 (层级, 标题文本)；非标题返回 (0, "")。"""
        stripped = text.lstrip()
        if not stripped.startswith("#"):
            return 0, ""
        level = len(stripped) - len(stripped.lstrip("#"))
        return level, stripped[level:].strip()

    @staticmethod
    def _make_table_segment(structured, table_html: str) -> Segment:
        """构造表格 Segment（可检索文本用 HTML，结构化数据存 payload）。"""
        html = table_html or ""
        return Segment(
            text=html,
            kind=SegmentKind.TABLE,
            tokens=count_tokens(html),
            table_html=html,
            payload=structured,
        )

    @staticmethod
    def _make_image_segment(description, media_ref: str) -> Segment:
        """构造图片 Segment（把描述包成带来源的可检索文本）。"""
        if description:
            text = f'[图片] {description}（来源: {media_ref}）'
        else:
            text = f'[图片]（来源: {media_ref}）'
        return Segment(
            text=text,
            kind=SegmentKind.IMAGE,
            tokens=count_tokens(text),
            media_ref=media_ref,
            payload=description,
        )

    @staticmethod
    def pack_blocks(
        segments: list[Segment],
        block_budget: int = BLOCK_TOKEN_BUDGET,
    ) -> list[Block]:
        """把有序 Segment 顺序打包成 Block（累加不超过 token 预算）。

        ``standalone`` 的 Segment 强制独立成块，不与前后拼接。
        """
        blocks: list[Block] = []

        for seg in segments:
            can_merge = (
                blocks
                and not seg.standalone
                and not (blocks[-1].segments and blocks[-1].segments[-1].standalone)
                and blocks[-1].tokens + seg.tokens <= block_budget
            )
            if can_merge:
                current = blocks[-1]
                current.text = f"{current.text}\n{seg.text}"
                current.tokens += seg.tokens + 1
                current.segments.append(seg)
            else:
                blocks.append(
                    Block(text=seg.text, tokens=seg.tokens,
                          segments=[seg], section=list(seg.section)),
                )

        # 去除首尾空白
        for block in blocks:
            block.text = block.text.strip()
            for seg in block.segments:
                seg.text = seg.text.strip()
        return blocks
