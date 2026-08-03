# -*- coding: utf-8 -*-
"""智能 Chunk 切分器：按 ## 标题层级切分 + 800 字符 + 80 重叠。

借鉴思路：来自九阳 POC 实战参数（chunk 800/80 + 按 ## 切分）。
所有算法均独立实现，不复制任何专有代码。
"""
from __future__ import annotations

import re
from typing import List

from app.rag.parsers.doc_types import ChildChunk, ElementType, ParentChunk

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
QA_PATTERN = re.compile(
    r"^Q[:：](.+?)\n\s*A[:：](.+?)$", re.MULTILINE | re.IGNORECASE
)


def _approx_tokens(text: str) -> int:
    """近似 token 数 = utf-8 字节数 // 4（与主流模型估算一致）。"""
    return len(text.encode("utf-8")) // 4


def split_markdown_by_heading(
    content: str, chunk_size: int = 800, chunk_overlap: int = 80
) -> List[str]:
    """按 Markdown ## 标题层级切分。

    1. 优先按 ## 切分（保留章节结构）
    2. 单章节超 chunk_size，按句号切
    3. 相邻 chunk 有 chunk_overlap 重叠
    """
    if not content or not content.strip():
        return []
    matches = list(HEADING_PATTERN.finditer(content))
    if not matches:
        return _split_by_sentence(content, chunk_size, chunk_overlap)
    matches.sort(key=lambda m: m.start())
    chunks: List[str] = []
    for i, m in enumerate(matches):
        section_start = m.start()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[section_start:section_end].strip()
        if len(section) <= chunk_size:
            if section:
                chunks.append(section)
        else:
            chunks.extend(_split_by_sentence(section, chunk_size, chunk_overlap))
    return [c for c in chunks if c.strip()]


def _split_by_sentence(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """按句号切分（带 overlap）。"""
    sentences = re.split(r"(?<=[。！？!?\n])", text)
    chunks: List[str] = []
    current = ""
    for sent in sentences:
        if not sent.strip():
            continue
        if len(current) + len(sent) <= chunk_size:
            current += sent
        else:
            if current:
                chunks.append(current.strip())
            if len(sent) > chunk_size:
                for i in range(0, len(sent), max(1, chunk_size - chunk_overlap)):
                    chunks.append(sent[i:i + chunk_size].strip())
                current = ""
            else:
                overlap = current[-chunk_overlap:] if len(current) > chunk_overlap else ""
                current = overlap + sent
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def extract_qa_pairs(content: str) -> List[dict]:
    """抽取 Q&A 速答段（九阳 POC 加分项）。"""
    return [
        {"question": m.group(1).strip(), "answer": m.group(2).strip()}
        for m in QA_PATTERN.finditer(content)
        if m.group(1).strip() and m.group(2).strip()
    ]


def merge_qa_into_chunks(chunks: List[str], qa_pairs: List[dict]) -> List[str]:
    """Q&A 速答段追加到 chunk（冗余编码）。"""
    if not qa_pairs or not chunks:
        return chunks
    qa_text = "\n\n【Q&A 速答】\n" + "\n".join(
        f"Q: {qa['question']}\nA: {qa['answer']}" for qa in qa_pairs
    )
    return [chunk + qa_text for chunk in chunks]


def build_child_chunks(
    sections: List[str],
    source_filename: str = "",
    document_id: str = "",
    tenant_id: str = "default",
    category: str = "general",
) -> List[ChildChunk]:
    """文本段 → ChildChunk 列表（带元数据）。"""
    return [
        ChildChunk(
            content=text,
            chunk_type=ElementType.TEXT,
            token_num=_approx_tokens(text),
            metadata={
                "document_id": document_id,
                "filename": source_filename,
                "tenant_id": tenant_id,
                "category": category,
                "chunk_index": idx,
                "chunk_total": len(sections),
            },
        )
        for idx, text in enumerate(sections)
        if text and text.strip()
    ]


def build_parent_chunks(
    child_chunks: List[ChildChunk],
    parent_chunk_size: int = 2000,
    source_filename: str = "",
    document_id: str = "",
    tenant_id: str = "default",
) -> List[ParentChunk]:
    """合并 child → parent（按 token 累加）。"""
    parents: List[ParentChunk] = []
    current_children: List[ChildChunk] = []
    current_tokens = 0
    for child in child_chunks:
        if current_tokens + child.token_num > parent_chunk_size and current_children:
            parents.append(ParentChunk(
                content="\n".join(c.content for c in current_children),
                token_num=current_tokens,
                child_chunks=current_children,
                metadata={"document_id": document_id, "filename": source_filename, "tenant_id": tenant_id},
            ))
            current_children = []
            current_tokens = 0
        current_children.append(child)
        current_tokens += child.token_num + 1
    if current_children:
        parents.append(ParentChunk(
            content="\n".join(c.content for c in current_children),
            token_num=current_tokens,
            child_chunks=current_children,
            metadata={"document_id": document_id, "filename": source_filename, "tenant_id": tenant_id},
        ))
    return parents
