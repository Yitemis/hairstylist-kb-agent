# -*- coding: utf-8 -*-
"""Context Compression: 压缩 RAG 召回的文档。

- BM25-based: 用 query 给 hits 排序, 取 top-k (无依赖, 快速)
- LLM-based: 用 LLM 总结压缩 (依赖 LLM, 慢但更好)
- Sentence-based: 句子级压缩 (折中方案)

配置化, 可关闭。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class CompressionMethod(str, Enum):
    """压缩方法。"""
    NONE = "none"               # 不压缩
    BM25_RERANK = "bm25"        # 用 query 对 hits 重排序 + top-k
    LLM_SUMMARY = "llm"          # LLM 总结
    SENTENCE_TOPK = "sentence"   # 句子级 top-k


@dataclass
class CompressedContext:
    """压缩后的上下文。"""
    text: str
    original_length: int
    compressed_length: int
    compression_ratio: float  # compressed / original
    method: CompressionMethod
    hit_count: int


def estimate_tokens(text: str) -> int:
    """粗略估计 token 数（中文 ~1.5 字符/token，英文 ~4 字符/token）。"""
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    other_chars = len(text) - chinese_chars
    return max(1, int(chinese_chars / 1.5 + other_chars / 4))


def split_sentences(text: str) -> List[str]:
    """简单分句（中英文）。"""
    # 中文分句: 。 ! ? ； 
    # 英文分句: . ! ?
    sentences = re.split(r"(?<=[。！？；!?\.])", text)
    return [s.strip() for s in sentences if s.strip()]


def keyword_score(sentence: str, keywords: List[str]) -> int:
    """句子含多少 query 关键词。"""
    sent_lower = sentence.lower()
    return sum(1 for kw in keywords if kw.lower() in sent_lower)


def sentence_bm25_compress(
    text: str,
    query: str,
    top_k: int = 5,
    max_chars: int = 2000,
) -> str:
    """句子级 BM25 压缩: 用 query 给句子排序, 取 top-k 句子。

    Args:
        text: 原始内容
        query: 用户问题
        top_k: 取 top-k 句子
        max_chars: 输出最大字符数

    Returns:
        压缩后的文本
    """
    sentences = split_sentences(text)
    if not sentences:
        return text[:max_chars]

    # 提取 query 关键词
    query_words = re.findall(r"[\w]+|[一-鿿]+", query)
    keywords = [w for w in query_words if len(w) > 1][:10]  # 限 10 个关键词

    if not keywords:
        return text[:max_chars]

    # 计算每个句子的分数 (关键词命中数 + 长度归一化)
    scored = [(s, keyword_score(s, keywords), len(s)) for s in sentences]
    # 排序: 分数降序, 同分按长度降序 (长句优先)
    scored.sort(key=lambda x: (-x[1], -x[2]))

    # 取 top-k (且分数 > 0)
    top_sentences = [s for s, score, _ in scored[:top_k] if score > 0]

    if not top_sentences:
        # 关键词命中 0, 取前几个句子
        top_sentences = sentences[:min(3, len(sentences))]

    # 拼回
    compressed = " ".join(top_sentences)
    if len(compressed) > max_chars:
        compressed = compressed[:max_chars]
    return compressed


def bm25_rerank_compress(
    hits: list,
    query: str,
    top_k: int = 5,
) -> list:
    """BM25-style rerank 压缩: 用 query 给 hits 重排序, 取 top-k。"""
    if len(hits) <= top_k:
        return hits

    query_words = re.findall(r"[\w]+|[一-鿿]+", query)
    keywords = [w.lower() for w in query_words if len(w) > 1][:10]

    if not keywords:
        return hits[:top_k]

    # 简单 rerank: keyword count, 命中数相同时长文档优先
    def score(hit):
        text = (getattr(hit, "content", "") or "").lower()
        kw_count = sum(1 for kw in keywords if kw in text)
        return (kw_count, len(text))  # 关键词数, 长度 (元组用于排序)

    reranked = sorted(hits, key=lambda h: score(h), reverse=True)
    return reranked[:top_k]


async def llm_summary_compress(
    hits: list,
    query: str,
    max_tokens: int = 500,
) -> str:
    """LLM 总结压缩: 用 LLM 总结多个 hits 的核心内容。

    借鉴 LLMLingua: 用 LLM 提取 query 相关内容, 压缩到 max_tokens。
    """
    if not hits:
        return ""
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg

    # 拼接所有 hits 内容
    context_text = "\n\n".join(
        f"[{i+1}] {h.content[:500]}" for i, h in enumerate(hits[:5])
    )

    system = f"""你是文本压缩专家。根据用户问题，从以下文档中提取最相关的信息，压缩到 {max_tokens} token 以内。

要求:
- 保留与问题直接相关的关键事实、数据、操作步骤
- 删除无关内容、重复内容、废话
- 保留原文措辞（如数字、术语）
- 输出纯文本，不要分点列表

用户问题: {query}

文档:
{context_text}"""

    model = get_model("chat")
    user_msg = UserMsg(name="user", content=[TextBlock(text=system)])
    sys_msg = UserMsg(name="system", content=[TextBlock(text="你是文本压缩专家。")])
    resp = await model([sys_msg, user_msg], stream=False)
    text = ""
    if hasattr(resp, "content") and resp.content:
        for block in resp.content:
            if hasattr(block, "text") and block.text:
                text += block.text
    return text.strip() or "\n\n".join(h.content[:300] for h in hits[:3])


async def compress_context(
    hits: list,
    query: str,
    method: CompressionMethod = CompressionMethod.BM25_RERANK,
    top_k: int = 5,
    max_tokens: int = 2000,
) -> CompressedContext:
    """压缩 RAG 召回的文档上下文。

    Args:
        hits: 召回的 hits 列表 (含 .content 字段)
        query: 用户问题
        method: 压缩方法
        top_k: 保留几个 hit / 句子
        max_tokens: 最大 token 数

    Returns:
        CompressedContext
    """
    if not hits:
        return CompressedContext(
            text="", original_length=0, compressed_length=0,
            compression_ratio=0.0, method=method, hit_count=0,
        )

    original_text = "\n\n".join(h.content for h in hits if h.content)
    original_length = len(original_text)

    if method == CompressionMethod.NONE:
        compressed = original_text
    elif method == CompressionMethod.BM25_RERANK:
        # Re-rank + top-k
        reranked = bm25_rerank_compress(hits, query, top_k=top_k)
        compressed = "\n\n".join(h.content for h in reranked if h.content)
    elif method == CompressionMethod.SENTENCE_TOPK:
        # 句子级压缩
        compressed = sentence_bm25_compress(original_text, query, top_k=5, max_chars=max_tokens * 4)
    elif method == CompressionMethod.LLM_SUMMARY:
        compressed = await llm_summary_compress(hits, query, max_tokens=max_tokens)
    else:
        compressed = original_text

    compressed_length = len(compressed)
    ratio = compressed_length / max(1, original_length)

    return CompressedContext(
        text=compressed,
        original_length=original_length,
        compressed_length=compressed_length,
        compression_ratio=ratio,
        method=method,
        hit_count=len(hits),
    )
