# -*- coding: utf-8 -*-
"""BM25 关键词检索通道。

向量检索擅长语义相近，但对型号、成分名、专业术语这类需要"精确字面命中"的
查询不稳定。BM25 基于词频统计做字面匹配，与向量检索互补，二者融合可显著提升
精确信息的召回率。

本模块维护一个内存 BM25 索引：文档以 ``(doc_id, text)`` 加入，检索返回按
BM25 分数排序的 ``(doc_id, score)``。分词见 :mod:`.tokenizer`。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .tokenizer import tokenize


@dataclass
class KeywordIndex:
    """内存 BM25 索引。

    适合单机 / 单租户规模。多租户时可为每个租户各建一个实例，或在检索后按
    元数据过滤（本项目在引擎层用 tenant 维度隔离）。
    """

    doc_ids: list[str] = field(default_factory=list)
    corpus_tokens: list[list[str]] = field(default_factory=list)
    _bm25: object = field(default=None, init=False, repr=False)

    def add(self, doc_id: str, text: str) -> None:
        """加入一篇文档（延迟构建索引，需调用 :meth:`build`）。"""
        self.doc_ids.append(doc_id)
        self.corpus_tokens.append(tokenize(text))
        self._bm25 = None  # 语料变更，索引失效

    def build(self) -> None:
        """基于当前语料构建 BM25 索引。"""
        from rank_bm25 import BM25Okapi

        if not self.corpus_tokens:
            self._bm25 = None
            return
        # rank_bm25 不接受空文档，空 token 用占位符兜底
        safe = [toks or ["_empty_"] for toks in self.corpus_tokens]
        self._bm25 = BM25Okapi(safe)

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """检索返回 ``(doc_id, bm25_score)``，按分数降序，最多 top_k 条。"""
        if self._bm25 is None:
            self.build()
        if self._bm25 is None:  # 语料为空
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(self.doc_ids, scores), key=lambda x: x[1], reverse=True,
        )
        return [(doc_id, float(score)) for doc_id, score in ranked[:top_k] if score > 0]

    def __len__(self) -> int:
        return len(self.doc_ids)
