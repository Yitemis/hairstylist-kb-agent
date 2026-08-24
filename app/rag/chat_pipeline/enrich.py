# -*- coding: utf-8 -*-
"""Enriched Passage: Rerank 前把标题 / 章节 / 来源拼到 passage 前.

基于 BGE Rerank + Enriched Passage 模式 (passage = 文档名 + 章节 + 内容)..

Why?
- Rerank 模型 (BGE / BAAI) 看到 "洗发水温控制标准" 比看到 raw content 更有用
- 带 "文档名 / 章节路径 / 来源" 后, rerank 能更好判断 "这段文本能不能回答这个问题"

Before:
    passage = hit.content[:500]  # 纯内容

After:
    passage = "文档: 美发技术手册\n章节: 染发技术 > 染前测试\n\nhit.content[:500]"
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Rerank 输入的安全上限 (防 base64 图片爆 token)
RERANK_SAFETY_MAX_CHARS = 8000

# 单个 passage 字符上限 (保护 rerank 模型输入)
DEFAULT_PASSAGE_MAX_CHARS = 1500


def get_enriched_passage(
    hit,
    source: Optional[str] = None,
    section_path: Optional[str] = None,
    document_id: Optional[str] = None,
    max_chars: int = DEFAULT_PASSAGE_MAX_CHARS,
) -> str:
    """构造 Enriched Passage (Rerank 用).

    Args:
        hit: RetrievalHit 或 dict
        source: 来源文件名 (覆盖 hit.source)
        section_path: 章节路径 (如 "染发技术 > 染前测试")
        document_id: 文档 ID
        max_chars: 内容最大字符数

    Returns:
        富化后的 passage 字符串

    Examples:
        >>> hit = {"content": "染前需做皮肤测试", "filename": "manual.pdf"}
        >>> get_enriched_passage(hit, section_path="染发技术")
        '文档: manual.pdf\n章节: 染发技术\n\n染前需做皮肤测试'
    """
    if isinstance(hit, dict):
        content = hit.get("content", "") or ""
        _source = source or hit.get("filename") or hit.get("source") or "unknown"
        _doc_id = document_id or hit.get("document_id", "")
    else:
        # RetrievalHit dataclass
        content = getattr(hit, "content", "") or ""
        _source = source or getattr(hit, "source", None) or "unknown"
        _doc_id = document_id or getattr(hit, "document_id", "")

    # 1. truncate content (防 token 爆炸)
    if len(content) > max_chars:
        content = content[:max_chars] + "..."

    # 2. 拼装: 文档 + 章节 + 内容
    parts = [f"文档: {_source}"]
    if section_path:
        parts.append(f"章节: {section_path}")
    elif _doc_id:
        parts.append(f"文档ID: {_doc_id}")
    parts.append("")  # 空行
    parts.append(content)

    return "\n".join(parts)


def get_enriched_passages_batch(
    hits: list,
    section_paths: Optional[list] = None,
    max_chars: int = DEFAULT_PASSAGE_MAX_CHARS,
) -> list:
    """批量构造 Enriched Passages.

    Args:
        hits: hit 列表
        section_paths: 章节路径列表 (与 hits 一一对应, 可为 None)
        max_chars: 单个 passage 最大字符数

    Returns:
        Enriched passage 字符串列表 (与 hits 顺序一致)
    """
    if section_paths is None:
        section_paths = [None] * len(hits)
    if len(section_paths) != len(hits):
        raise ValueError(
            f"section_paths length ({len(section_paths)}) "
            f"!= hits length ({len(hits)})",
        )

    return [
        get_enriched_passage(h, section_path=sp, max_chars=max_chars)
        for h, sp in zip(hits, section_paths)
    ]


def sanitize_passage_for_rerank(
    passage: str,
    max_total_chars: int = RERANK_SAFETY_MAX_CHARS,
) -> str:
    """Passage 安全保护: 删除 base64 图片 + 截断.

    删除 base64 图片 + 截断过长文本./

    Args:
        passage: 原始 passage
        max_total_chars: 最大字符数

    Returns:
        安全的 passage
    """
    from app.rag.utils.sanitize import sanitize_for_embedding
    safe = sanitize_for_embedding(passage)
    if len(safe) > max_total_chars:
        safe = safe[:max_total_chars]
    return safe


__all__ = [
    "DEFAULT_PASSAGE_MAX_CHARS",
    "RERANK_SAFETY_MAX_CHARS",
    "get_enriched_passage",
    "get_enriched_passages_batch",
    "sanitize_passage_for_rerank",
]
