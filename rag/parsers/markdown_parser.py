# -*- coding: utf-8 -*-
"""Markdown 解析器（.md）。

采用逐行扫描的状态机把 Markdown 拆成有序元素，再按标题层级组织成 Block：

1. 扫描每一行，识别代码围栏（```）、管道表格、独立图片与普通文本，
   围栏与表格作为跨行块整体收集；
2. 行内图片先抽出转成图片元素，其余留作文本；
3. 表格渲染成 HTML 后交模型结构化，图片交模型描述；
4. 组块时以标题另起一个 Block，其后内容归入当前标题，代码块整体保留。
"""
from __future__ import annotations

import logging
import re

from markdown import markdown

from .base import BaseParser, count_tokens
from .doc_types import Block, Segment, SegmentKind
from .utils import get_text
from . import vlm

logger = logging.getLogger(__name__)

# 行内 / 独立图片匹配
_MD_IMAGE = re.compile(r'!\[(?P<alt>.*?)\]\((?P<url>[^)\s]+)(?:\s+"(?P<title>.*?)")?\)')
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_IMG_SRC = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_ALT = re.compile(r'alt=["\']([^"\']*)["\']', re.IGNORECASE)

# 表格分隔行，例如 | --- | :--: |
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

# 元素类型标签（本模块内部使用）
_EL_HEADING = "heading"
_EL_TEXT = "text"
_EL_CODE = "code"
_EL_TABLE = "table"
_EL_IMAGE = "image"


class MarkdownParser(BaseParser):
    """Markdown 解析器。"""

    def load(self) -> list[Block]:
        """解析 Markdown 文件。"""
        raw = get_text("", self._read_binary()) if self.file_url else get_text(self.file_path)
        lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        elements = self._scan(lines)
        return self._assemble(elements)

    # ------------------------------------------------------------------
    # 第一步：逐行扫描成有序元素 (tag, value)
    # ------------------------------------------------------------------

    def _scan(self, lines: list[str]) -> list[tuple[str, object]]:
        """把行序列扫描成元素序列。"""
        elements: list[tuple[str, object]] = []
        i, n = 0, len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 空行跳过
            if not stripped:
                i += 1
                continue

            # 代码围栏：收集到配对的 ``` 为止，整体作为一个元素
            if stripped.startswith("```"):
                fence, i = self._take_code_fence(lines, i)
                elements.append((_EL_CODE, fence))
                continue

            # 管道表格：当前行含 |，且下一行是分隔行
            if "|" in line and i + 1 < n and _TABLE_RULE.match(lines[i + 1]):
                table_md, i = self._take_pipe_table(lines, i)
                elements.append((_EL_TABLE, table_md))
                continue

            # 独立图片行（整行就是一张图）
            only_image = self._as_standalone_image(stripped)
            if only_image is not None:
                elements.append((_EL_IMAGE, only_image))
                i += 1
                continue

            # 普通文本行：先抽出行内图片，剩余部分作为文本/标题
            text, inline_images = self._extract_inline_images(stripped)
            if text.strip():
                tag = _EL_HEADING if text.lstrip().startswith("#") else _EL_TEXT
                elements.append((tag, text.strip()))
            for img in inline_images:
                elements.append((_EL_IMAGE, img))
            i += 1

        return elements

    @staticmethod
    def _take_code_fence(lines: list[str], start: int) -> tuple[str, int]:
        """从围栏起始行收集整段代码，返回 (代码文本, 下一行索引)。"""
        collected = [lines[start]]
        j = start + 1
        while j < len(lines):
            collected.append(lines[j])
            if lines[j].strip().startswith("```"):
                j += 1
                break
            j += 1
        return "\n".join(collected), j

    @staticmethod
    def _take_pipe_table(lines: list[str], start: int) -> tuple[str, int]:
        """收集连续的管道表格行，返回 (表格 Markdown, 下一行索引)。"""
        collected = [lines[start]]
        j = start + 1
        while j < len(lines) and "|" in lines[j] and lines[j].strip():
            collected.append(lines[j])
            j += 1
        return "\n".join(collected), j

    @classmethod
    def _as_standalone_image(cls, line: str) -> dict | None:
        """若整行恰好是一张图片，返回其信息，否则 None。"""
        md = _MD_IMAGE.fullmatch(line)
        if md:
            return {"url": md.group("url"),
                    "alt": md.group("alt"), "title": md.group("title") or ""}
        if _HTML_IMAGE.fullmatch(line):
            src = _IMG_SRC.search(line)
            if src:
                alt = _IMG_ALT.search(line)
                return {"url": src.group(1), "alt": alt.group(1) if alt else "", "title": ""}
        return None

    @classmethod
    def _extract_inline_images(cls, line: str) -> tuple[str, list[dict]]:
        """抽出行内图片，返回 (去图后的文本, 图片信息列表)。"""
        found: list[dict] = []

        def _md_repl(m: re.Match) -> str:
            found.append({"url": m.group("url"),
                          "alt": m.group("alt"), "title": m.group("title") or ""})
            return ""

        text = _MD_IMAGE.sub(_md_repl, line)

        def _html_repl(m: re.Match) -> str:
            src = _IMG_SRC.search(m.group(0))
            if src:
                alt = _IMG_ALT.search(m.group(0))
                found.append({"url": src.group(1),
                              "alt": alt.group(1) if alt else "", "title": ""})
            return ""

        text = _HTML_IMAGE.sub(_html_repl, text)
        return text, found

    # ------------------------------------------------------------------
    # 第二步：元素 -> Segment -> Block（标题分组，代码块整体）
    # ------------------------------------------------------------------

    def _assemble(self, elements: list[tuple[str, object]]) -> list[Block]:
        """把元素序列组装成 Block，并沿途维护章节路径。"""
        # heading_stack[i] 记录第 i+1 级标题的当前标题文本
        heading_stack: list[str] = []
        segments: list[Segment] = []

        for tag, value in elements:
            if tag == _EL_HEADING:
                level, title = self._heading_level(str(value))
                # 截断到上级，再压入当前级，形成从根到当前的路径
                heading_stack = heading_stack[: level - 1]
                while len(heading_stack) < level - 1:
                    heading_stack.append("")  # 跨级标题的空档补位
                heading_stack.append(title)

            segment = self._to_segment(tag, value)
            if segment is None:
                continue
            # 标题所在段的 section 为其父级路径；正文段为当前完整路径
            if tag == _EL_HEADING:
                segment.section = [h for h in heading_stack[:-1] if h]
            else:
                segment.section = [h for h in heading_stack if h]
            segments.append(segment)

        return self._group_by_heading(segments)

    @staticmethod
    def _heading_level(text: str) -> tuple[int, str]:
        """解析标题行，返回 (层级, 纯标题文本)。"""
        stripped = text.lstrip()
        level = len(stripped) - len(stripped.lstrip("#"))
        title = stripped[level:].strip()
        return max(level, 1), title

    def _to_segment(self, tag: str, value: object) -> Segment | None:
        """把单个元素转成 Segment。"""
        if tag in (_EL_HEADING, _EL_TEXT):
            text = str(value)
            return Segment(text=text, kind=SegmentKind.TEXT, tokens=count_tokens(text))

        if tag == _EL_CODE:
            code = str(value)
            # 代码块整体保留、不与相邻文本合并
            return Segment(text=code, kind=SegmentKind.TEXT,
                           tokens=count_tokens(code), standalone=True)

        if tag == _EL_TABLE:
            html = markdown(str(value), extensions=["markdown.extensions.tables"])
            structured = vlm.structure_table(html)
            return self._make_table_segment(structured, html)

        if tag == _EL_IMAGE:
            info: dict = value  # type: ignore[assignment]
            hint = "；".join(
                part for part in (
                    f"注释：{info['alt']}" if info.get("alt") else "",
                    f"标题：{info['title']}" if info.get("title") else "",
                ) if part
            )
            description = vlm.describe_image(info["url"], extra_hint=hint)
            return self._make_image_segment(description, info["url"])

        return None

    @staticmethod
    def _group_by_heading(segments: list[Segment], block_budget: int = 512) -> list[Block]:
        """标题开启新块，其后内容归入当前块；超预算或独立段则另起块。"""
        blocks: list[Block] = []

        def _is_heading(seg: Segment) -> bool:
            return seg.kind == SegmentKind.TEXT and seg.text.lstrip().startswith("#")

        for seg in segments:
            prev = blocks[-1] if blocks else None
            prev_standalone = bool(prev and prev.segments and prev.segments[-1].standalone)

            start_new = (
                prev is None
                or _is_heading(seg)
                or seg.standalone
                or prev_standalone
                or prev.tokens + seg.tokens > block_budget
            )

            if start_new:
                blocks.append(
                    Block(text=seg.text, tokens=seg.tokens,
                          segments=[seg], section=list(seg.section)),
                )
            else:
                prev.text = f"{prev.text}\n{seg.text}"
                prev.tokens += seg.tokens + 1
                prev.segments.append(seg)

        for block in blocks:
            block.text = block.text.strip()
        return blocks
