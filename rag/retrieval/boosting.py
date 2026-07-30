# -*- coding: utf-8 -*-
"""检索后重排加权：类型加权 + 型号精确匹配加权。

融合排序之后，再依据查询意图与文档元数据做定向提权：

* 类型加权：查询含"图/图片"时提升图片类结果，含"表/表格/参数/价格"时提升
  表格类结果，让跨模态查询更易命中对应内容；
* 型号加权：查询中出现的型号/编码若命中文档，则大幅提权，保证精确信息优先。

加权以"分数 + 增量"的方式作用于已归一化到 [0,1] 的融合分。
"""
from __future__ import annotations

import re

from .tokenizer import extract_models

# 触发类型加权的查询关键词
_IMAGE_HINTS = ("图", "图片", "照片", "示意图", "面板")
_TABLE_HINTS = ("表", "表格", "参数", "配比", "价格", "清单", "列表", "规格")

# 各项加权增量（可按业务调参）
BOOST_TYPE = 0.15
BOOST_MODEL = 0.25


def wants_image(query: str) -> bool:
    """查询是否偏向图片类内容。"""
    return any(h in query for h in _IMAGE_HINTS)


def wants_table(query: str) -> bool:
    """查询是否偏向表格类内容。"""
    return any(h in query for h in _TABLE_HINTS)


def apply_boosts(
    query: str,
    scored: list[tuple[str, float]],
    kinds_of: dict[str, set[str]],
    text_of: dict[str, str],
) -> list[tuple[str, float]]:
    """对候选结果应用类型与型号加权，返回重排后的结果。

    Args:
        query: 用户查询。
        scored: 融合后的 ``(doc_id, score)``，score 建议已归一化到 [0,1]。
        kinds_of: doc_id -> 其包含的内容形态集合（如 {"text","image"}）。
        text_of: doc_id -> 其可检索文本（用于型号命中判断）。

    Returns:
        加权并重新降序排序后的 ``(doc_id, score)``。
    """
    query_models = set(extract_models(query))
    like_image = wants_image(query)
    like_table = wants_table(query)

    boosted: list[tuple[str, float]] = []
    for doc_id, score in scored:
        kinds = kinds_of.get(doc_id, set())

        if like_image and "image" in kinds:
            score += BOOST_TYPE
        if like_table and "table" in kinds:
            score += BOOST_TYPE

        if query_models:
            doc_models = set(extract_models(text_of.get(doc_id, "")))
            if query_models & doc_models:
                score += BOOST_MODEL

        boosted.append((doc_id, score))

    boosted.sort(key=lambda x: x[1], reverse=True)
    return boosted
