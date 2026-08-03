# -*- coding: utf-8 -*-
"""文档元素类型与父子分块数据模型。

借鉴 ekbs-ai-service 的设计：
- ChildChunk：检索单位（子块），携带原始资源（图片 URL、HTML 表格）
- ParentChunk：上下文单位（父块），给 LLM 看完整段落
- Token-based 切分 + 父子关联
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ElementType:
    """元素类型。"""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    AUDIO = "audio"
    EQUATION = "equation"


@dataclass
class ChildChunk:
    """子块（检索单位，用于 embedding 相似度匹配）。

    Attributes:
        content: 子块文本（用于 embedding 和检索）
        chunk_type: 元素类型（TEXT/TABLE/IMAGE/AUDIO）
        token_num: token 数
        html_table: HTML 表格（保留结构，TABLE 类型时使用）
        image_url: 图片 URL（IMAGE 类型时使用）
        image_info: 图片 VLM 描述（IMAGE 类型时使用）
        table_info_list: 表格数据（LLM 拆解后，TABLE 类型时使用）
        audio_url: 音频 URL（AUDIO 类型时使用）
        is_ignore: 是否跳过（如空白块）
    """
    content: str
    chunk_type: str = ElementType.TEXT
    token_num: int = 0
    html_table: str | None = None
    image_url: str | None = None
    image_info: str | None = None
    table_info_list: list[dict] | None = None
    audio_url: str | None = None
    is_ignore: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParentChunk:
    """父块（context 单位，丢给 LLM 看完整段落）。

    Attributes:
        content: 父块完整文本
        token_num: token 数
        child_chunks: 包含的子块列表
        metadata: 元数据（chapter、page、permission_tag 等）
    """
    content: str
    token_num: int = 0
    child_chunks: list[ChildChunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
