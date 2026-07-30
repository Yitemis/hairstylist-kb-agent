# -*- coding: utf-8 -*-
"""解析结果的数据模型。

所有格式的解析器都产出统一的两层结构：

- :class:`Segment`  —— 检索粒度。文档被切成的最小单元，直接用于向量化召回。
- :class:`Block`    —— 上下文粒度。若干相邻 Segment 聚合而成，命中后回填给
  模型作为完整上下文。

两层分离的目的：小粒度保证向量检索精度，大粒度保证回答时上下文完整。
非文本内容（表格、图片、音频）先经模型转成可检索文本，再纳入同一结构，
原始载体（表格 HTML、媒体地址、结构化数据）保存在 Segment 的对应字段里。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SegmentKind(str, Enum):
    """Segment 的内容形态。"""

    TEXT = "text"    # 文字（正文、标题、代码等）
    TABLE = "table"  # 表格
    IMAGE = "image"  # 图片
    AUDIO = "audio"  # 音频


@dataclass
class Segment:
    """检索单元。

    Attributes:
        text: 可检索文本。表格/图片/音频存放其转写或语义描述。
        kind: 内容形态，见 :class:`SegmentKind`。
        tokens: ``text`` 的 token 数，供聚合时控制粒度。
        table_html: 表格原始 HTML（仅表格 Segment）。
        media_ref: 媒体地址或路径（图片 / 音频 Segment）。
        payload: 结构化附加数据（表格解析出的行数据、图片的原始描述等）。
        standalone: 为真时不与相邻 Segment 拼接，独立成块（如代码块）。
        section: 所属章节路径（面包屑），如 ["洗护产品", "选购指南"]，
            用于章节定向召回；无标题结构时为空列表。
    """

    text: str
    kind: SegmentKind
    tokens: int
    table_html: str | None = None
    media_ref: str | None = None
    payload: Any = None
    standalone: bool = False
    section: list[str] = field(default_factory=list)


@dataclass
class Block:
    """上下文单元，由一组相邻 Segment 组成。

    Attributes:
        text: 块内全部 Segment 拼接后的完整文本。
        tokens: ``text`` 的 token 总数。
        segments: 组成该块的 Segment 列表（保持文档顺序）。
        section: 该块所属章节路径（面包屑），取块内首个 Segment 的 section。
        metadata: 索引期附加的自由元数据（型号、权限标签等），
            由上层管道按需填充。
    """

    text: str
    tokens: int
    segments: list[Segment] = field(default_factory=list)
    section: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def kinds(self) -> set[SegmentKind]:
        """块内所含内容形态集合（供类型加权检索使用）。"""
        return {seg.kind for seg in self.segments}
