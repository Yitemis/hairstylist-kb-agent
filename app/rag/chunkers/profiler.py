# -*- coding: utf-8 -*-
"""文档 Profiler: 扫描文档结构, 提取 17 维特征.

借鉴 WeKnora chunker/profiler.go (Section 2.2).

Profile 输出 -> 传给 strategy.py 自动选 Tier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


# MD 标题正则: # / ## / ### ...
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
# 数字章节: 1.1 / 2.3.4
_NUMBERED_SECTION_RE = re.compile(r"^\d+(\.\d+)+\s+\S", re.MULTILINE)
# 分页符
_FORM_FEED_RE = re.compile(r"\f")
# 代码块
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
# 表格行: | xxx | yyy |
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
# 公式 (简单检测: $$ ... $$)
_EQUATION_RE = re.compile(r"\$\$[\s\S]*?\$\$", re.MULTILINE)
# mermaid
_MERMAID_RE = re.compile(r"```mermaid", re.IGNORECASE)


@dataclass
class DocProfile:
    """文档结构 profile (借鉴 WeKnora DocProfile)."""
    total_chars: int = 0
    total_lines: int = 0
    md_heading_counts: Dict[int, int] = field(default_factory=dict)  # level -> count
    has_tables: bool = False
    table_line_count: int = 0
    has_code: bool = False
    code_block_count: int = 0
    has_mermaid: bool = False
    has_equations: bool = False
    equation_count: int = 0
    numbered_section_count: int = 0
    form_feed_count: int = 0
    detected_langs: List[str] = field(default_factory=list)
    code_ratio: float = 0.0  # 代码行 / 总行数
    avg_line_length: float = 0.0
    # 派生: 选 Tier 的依据
    recommended_tier: int = 3  # 1/2/3, default fallback
    recommended_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "total_chars": self.total_chars,
            "total_lines": self.total_lines,
            "md_heading_counts": dict(self.md_heading_counts),
            "has_tables": self.has_tables,
            "table_line_count": self.table_line_count,
            "has_code": self.has_code,
            "code_block_count": self.code_block_count,
            "has_mermaid": self.has_mermaid,
            "has_equations": self.has_equations,
            "equation_count": self.equation_count,
            "numbered_section_count": self.numbered_section_count,
            "form_feed_count": self.form_feed_count,
            "detected_langs": list(self.detected_langs),
            "code_ratio": round(self.code_ratio, 3),
            "avg_line_length": round(self.avg_line_length, 1),
            "recommended_tier": self.recommended_tier,
            "recommended_reason": self.recommended_reason,
        }


def _detect_languages(text: str) -> List[str]:
    """检测文档语言 (简单启发式)."""
    langs = []
    if re.search(r"[一-鿿]", text):
        langs.append("zh")
    if re.search(r"[a-zA-Z]{4,}", text):
        langs.append("en")
    return langs or ["unknown"]


def profile_document(content: str) -> DocProfile:
    """扫描文档, 生成 DocProfile.

    Args:
        content: 文档全文 (Markdown 优先, 纯文本也可)

    Returns:
        DocProfile 对象, 含 17 维特征 + 推荐 Tier
    """
    if not content:
        p = DocProfile()
        p.recommended_tier = 3
        p.recommended_reason = "empty document"
        return p

    p = DocProfile()
    p.total_chars = len(content)
    lines = content.split("\n")
    p.total_lines = len(lines)
    p.avg_line_length = p.total_chars / max(1, p.total_lines)

    # 1. MD heading 统计
    for m in _HEADING_RE.finditer(content):
        level = len(m.group(1))
        p.md_heading_counts[level] = p.md_heading_counts.get(level, 0) + 1

    # 2. 表格检测
    table_lines = _TABLE_ROW_RE.findall(content)
    p.table_line_count = len(table_lines)
    p.has_tables = p.table_line_count >= 2  # 至少 2 行才算表格

    # 3. 代码块
    code_blocks = _FENCED_CODE_RE.findall(content)
    p.code_block_count = len(code_blocks)
    p.has_code = p.code_block_count > 0
    p.has_mermaid = bool(_MERMAID_RE.search(content))

    # 4. 公式
    equations = _EQUATION_RE.findall(content)
    p.equation_count = len(equations)
    p.has_equations = p.equation_count > 0

    # 5. 数字章节
    p.numbered_section_count = len(_NUMBERED_SECTION_RE.findall(content))

    # 6. 分页符
    p.form_feed_count = len(_FORM_FEED_RE.findall(content))

    # 7. 语言
    p.detected_langs = _detect_languages(content)

    # 8. 代码占比
    if code_blocks:
        code_chars = sum(len(b) for b in code_blocks)
        p.code_ratio = code_chars / max(1, p.total_chars)

    return p


__all__ = ["DocProfile", "profile_document"]
