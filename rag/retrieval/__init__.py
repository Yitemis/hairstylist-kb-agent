# -*- coding: utf-8 -*-
"""混合检索工具集。

组合三种能力提升检索质量（可独立使用、也可组合成流水线）：

* :mod:`.keyword`   —— BM25 关键词通道，补齐向量检索的精确匹配短板；
* :mod:`.fusion`    —— RRF 融合多路召回结果，对齐不同通道的分数量纲；
* :mod:`.boosting`  —— 按查询意图对类型 / 型号做定向加权重排；
* :mod:`.tokenizer` —— 中英文混合分词，保留型号 / 编码等专有 token。

本层为纯算法、无外部服务依赖，便于离线测试；向量通道由 RAG 引擎接入后与此
处能力组合。
"""
from __future__ import annotations

from .boosting import apply_boosts, wants_image, wants_table
from .fusion import reciprocal_rank_fusion
from .keyword import KeywordIndex
from .tokenizer import extract_models, tokenize

__all__ = [
    "KeywordIndex",
    "reciprocal_rank_fusion",
    "apply_boosts",
    "wants_image",
    "wants_table",
    "tokenize",
    "extract_models",
]
