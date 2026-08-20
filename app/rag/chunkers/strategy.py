# -*- coding: utf-8 -*-
"""3 Tier 自适应分块策略选择器.

借鉴 WeKnora chunker/strategy.go (Section 2.1).

Tier 1 (Heading-aware):   ## 标题 >= 3, 有清晰章节结构
Tier 2 (Heuristic):       启发式标记: 数字章节 / 分页符 / 多语言
Tier 3 (Recursive):       fallback, 按 \n -> 。-> 空格 递归切
"""
from __future__ import annotations

import logging
import re
from typing import List

from app.rag.chunkers.profiler import DocProfile, profile_document

logger = logging.getLogger(__name__)


# Tier 阈值 (借鉴 WeKnora strategy.go)
TIER1_HEADING_MIN = 3  # 至少 3 个 H1-H6 标题
TIER1_TOTAL_HEADING_MIN = 5  # 至少 5 个标题层级 (所有 level 合计)
TIER2_NUMBERED_MIN = 3  # 至少 3 个数字章节
TIER2_FORM_FEED_MIN = 2  # 至少 2 个分页符


def select_tier(profile: DocProfile) -> int:
    """根据 profile 选 Tier.

    Returns:
        1 / 2 / 3
    """
    total_headings = sum(profile.md_heading_counts.values())

    # Tier 1: 有清晰标题结构
    h1_h2 = profile.md_heading_counts.get(1, 0) + profile.md_heading_counts.get(2, 0)
    if h1_h2 >= TIER1_HEADING_MIN or total_headings >= TIER1_TOTAL_HEADING_MIN:
        return 1

    # Tier 2: 启发式标记
    if (
        profile.numbered_section_count >= TIER2_NUMBERED_MIN
        or profile.form_feed_count >= TIER2_FORM_FEED_MIN
        or len(profile.detected_langs) >= 2  # 多语言
    ):
        return 2

    # Tier 3: fallback
    return 3


def explain_tier_choice(profile: DocProfile) -> str:
    """解释为什么选这个 tier (用于 debug)."""
    tier = select_tier(profile)
    if tier == 1:
        total = sum(profile.md_heading_counts.values())
        h12 = profile.md_heading_counts.get(1, 0) + profile.md_heading_counts.get(2, 0)
        return f"Tier 1 (heading): H1+H2={h12}, total headings={total}"
    elif tier == 2:
        return (
            f"Tier 2 (heuristic): numbered={profile.numbered_section_count}, "
            f"form_feed={profile.form_feed_count}, langs={profile.detected_langs}"
        )
    else:
        return "Tier 3 (recursive fallback)"


def profile_and_select(content: str) -> tuple[DocProfile, int]:
    """一步到位: profile + select tier.

    Args:
        content: 文档内容

    Returns:
        (profile, tier)
    """
    profile = profile_document(content)
    tier = select_tier(profile)
    profile.recommended_tier = tier
    profile.recommended_reason = explain_tier_choice(profile)
    logger.info(
        "Doc profile: chars=%d lines=%d headings=%s -> Tier %d (%s)",
        profile.total_chars, profile.total_lines,
        dict(profile.md_heading_counts), tier, profile.recommended_reason,
    )
    return profile, tier


# ===================================================================
# 3 个 Tier 的 chunker 实现 (包装 smart_chunker)
# ===================================================================

def chunk_with_tier(
    content: str,
    profile: DocProfile,
    tier: int,
    chunk_size: int = 800,
    chunk_overlap: int = 80,
) -> List[str]:
    """根据 tier 选 chunker 切分文档.

    Args:
        content: 文档内容
        profile: 文档 profile (用于 Tier 2/3 调整)
        tier: 1/2/3
        chunk_size: chunk 大小
        chunk_overlap: chunk 重叠

    Returns:
        chunk 文本列表
    """
    # Lazy import 避免循环
    from app.rag.chunkers.smart_chunker import (
        split_markdown_by_heading,
        _split_by_sentence,
    )

    if tier == 1:
        # Tier 1: heading-aware
        return split_markdown_by_heading(content, chunk_size, chunk_overlap)

    elif tier == 2:
        # Tier 2: heuristic
        # - 先按分页符 / 数字章节粗切
        # - 再贪心 bin-packing 到 chunk_size
        coarse_sections = _split_by_heuristic_marks(content, profile)
        return _bin_pack(coarse_sections, chunk_size, chunk_overlap)

    else:
        # Tier 3: recursive
        return _split_recursive(content, chunk_size, chunk_overlap)


def _split_by_heuristic_marks(content: str, profile: DocProfile) -> List[str]:
    """Tier 2 第一步: 按启发式标记粗切.

    优先级: 分页符 > 数字章节 > 段落 (双换行)
    """
    if profile.form_feed_count >= TIER2_FORM_FEED_MIN:
        # 按分页符切
        return [s.strip() for s in content.split("\f") if s.strip()]

    if profile.numbered_section_count >= TIER2_NUMBERED_MIN:
        # 按数字章节切 (简单: 找 "1.1 xxx" 之类作为起点)
        parts = re.split(r"(?=^\d+\.\d+)", content, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    # fallback: 段落
    return [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]


def _bin_pack(sections: List[str], chunk_size: int, chunk_overlap: int) -> List[str]:
    """Tier 2 第二步: 贪心 bin-packing."""
    chunks: List[str] = []
    current = ""
    for sec in sections:
        if len(current) + len(sec) + 1 <= chunk_size:
            current = (current + "\n" + sec).strip() if current else sec
        else:
            if current.strip():
                chunks.append(current.strip())
            if len(sec) > chunk_size:
                # 单段超过 chunk_size, 递归切句
                from app.rag.chunkers.smart_chunker import _split_by_sentence
                chunks.extend(_split_by_sentence(sec, chunk_size, chunk_overlap))
                current = ""
            else:
                overlap = current[-chunk_overlap:] if len(current) > chunk_overlap else ""
                current = overlap + sec
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def _split_recursive(
    content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    """Tier 3: 递归按 \n -> 。-> 空格 切.

    借鉴 WeKnora recursive fallback.
    """
    from app.rag.chunkers.smart_chunker import _split_by_sentence
    return _split_by_sentence(content, chunk_size, chunk_overlap)


__all__ = [
    "TIER1_HEADING_MIN",
    "TIER1_TOTAL_HEADING_MIN",
    "TIER2_FORM_FEED_MIN",
    "TIER2_NUMBERED_MIN",
    "chunk_with_tier",
    "explain_tier_choice",
    "profile_and_select",
    "select_tier",
]
