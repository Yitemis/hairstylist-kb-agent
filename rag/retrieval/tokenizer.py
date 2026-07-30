# -*- coding: utf-8 -*-
"""检索分词：中英文混合切词，保留型号 / 编码等专有 token。

关键词检索（BM25）依赖分词质量。中文用 jieba 切词；同时把型号、零件号、
成分名这类"字母+数字"组合作为整体保留（如 ``K7Pro``、``Y968``），避免被
拆碎导致精确查询召回失败——这正是命中率的关键。
"""
from __future__ import annotations

import re

# 型号 / 编码：字母与数字混排的连续串（长度≥2），大小写不敏感
_MODEL_TOKEN = re.compile(r"[A-Za-z]+[A-Za-z0-9]*\d[A-Za-z0-9]*|\d+[A-Za-z]+[A-Za-z0-9]*")
# 纯英文单词
_WORD = re.compile(r"[A-Za-z]{2,}")

# 常见停用词（检索噪声），可按需扩充
_STOPWORDS = frozenset({
    "的", "了", "是", "在", "和", "与", "我", "你", "他", "它",
    "吗", "呢", "啊", "怎么", "如何", "什么", "哪些", "这个", "那个",
    "a", "an", "the", "of", "to", "is", "are", "and", "or",
})

_jieba_ready = False


def _ensure_jieba():
    """惰性初始化 jieba（首次调用时加载词典）。"""
    global _jieba_ready
    import jieba

    if not _jieba_ready:
        jieba.initialize()
        _jieba_ready = True
    return jieba


def extract_models(text: str) -> list[str]:
    """抽取文本中的型号 / 编码 token（小写归一）。"""
    return [m.lower() for m in _MODEL_TOKEN.findall(text)]


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    """把文本切成检索 token。

    步骤：先抽出型号/编码整体保护，其余部分交 jieba 切词，最后统一小写、
    去停用词与纯空白。

    Args:
        text: 原始文本。
        keep_stopwords: 是否保留停用词（默认去除）。

    Returns:
        token 列表（小写）。
    """
    if not text:
        return []

    tokens: list[str] = []

    # 1) 先取出型号/编码，占位后避免被 jieba 拆碎
    protected = extract_models(text)
    masked = _MODEL_TOKEN.sub(" ", text)

    # 2) jieba 切词
    jieba = _ensure_jieba()
    for piece in jieba.lcut(masked):
        piece = piece.strip().lower()
        if not piece:
            continue
        tokens.append(piece)

    tokens.extend(protected)

    # 3) 过滤
    result = []
    for tok in tokens:
        if not tok or tok.isspace():
            continue
        if not keep_stopwords and tok in _STOPWORDS:
            continue
        result.append(tok)
    return result
