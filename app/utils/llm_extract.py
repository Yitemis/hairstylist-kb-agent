# -*- coding: utf-8 -*-
"""LLM 响应文本抽取 helper (P2-1: 消除 5 处重复的 for blk in resp.content)。"""
from __future__ import annotations

from typing import Any


def extract_text(resp: Any) -> str:
    """从 LLM/Agent 响应中抽取纯文本。

    兼容多种响应格式:
    - resp.content 是 list[TextBlock]
    - resp.content 是 str (少数模型)
    - resp 是 async iterator (流式)
    - resp 是 dict (有 'content' 字段)

    Returns:
        拼接后的纯文本，无内容返回 ""
    """
    if resp is None:
        return ""

    # 字典格式
    if isinstance(resp, dict):
        content = resp.get("content") or resp.get("text") or ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return _blocks_to_text(content)
        return str(content)

    # 字符串格式
    if isinstance(resp, str):
        return resp

    # 异步流式迭代器
    if hasattr(resp, "__aiter__"):
        # 不会在这里跑异步，统一返回空（让调用方自己处理）
        return ""

    # 标准对象格式
    text = ""
    content = getattr(resp, "content", None)
    if content is None:
        return str(resp) if resp else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text = _blocks_to_text(content)

    # 兜底：从 metadata 找 text 字段
    if not text:
        metadata = getattr(resp, "metadata", None)
        if isinstance(metadata, dict):
            text = metadata.get("text", "") or ""

    return text


def _blocks_to_text(blocks) -> str:
    """从 ContentBlock 列表拼文本。"""
    parts = []
    for blk in blocks:
        if isinstance(blk, str):
            parts.append(blk)
        elif isinstance(blk, dict):
            t = blk.get("text") or blk.get("content") or ""
            if t:
                parts.append(t)
        else:
            t = getattr(blk, "text", None) or getattr(blk, "content", None)
            if t:
                parts.append(str(t))
    return "".join(parts)
