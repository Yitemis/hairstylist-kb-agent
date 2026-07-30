# -*- coding: utf-8 -*-
"""检索运行时：混合检索 + 父块聚合 + Rerank 精排。

把纯算法层（BM25 / RRF / 加权）与在线服务（Milvus 向量召回、Rerank 模型）
组装成完整的两阶段检索：

1. 向量召回：查询向量化 → Milvus 取 Top-N 子块（租户硬过滤）；
2. 关键词召回：BM25 在候选子块上打分；
3. 融合：RRF 合并两路子块排名；
4. 父块聚合：同一父块取最高分子块，回溯父块全文（父子分块回溯）；
5. 加权：按查询意图对型号 / 类型定向提权；
6. 精排：可选 Rerank 交叉编码器对父块做最终排序。

对外暴露 :func:`search` 协程，返回父块级 :class:`SearchHit` 列表。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rag.retrieval import (
    KeywordIndex,
    apply_boosts,
    reciprocal_rank_fusion,
)
from rag.retrieval.tokenizer import extract_models

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    """父块级检索结果。

    Attributes:
        parent_id: 父块 ID。
        text: 父块完整文本（作为上下文交给模型）。
        matched_text: 命中的子块文本（可用于高亮 / 调试）。
        score: 最终得分。
        filename: 来源文件名。
        section_path: 章节路径。
        category: 业务分类。
        kinds: 该父块被召回子块所含内容形态。
        rerank_applied: 是否经过 Rerank 精排。
    """

    parent_id: str
    text: str
    matched_text: str
    score: float
    filename: str
    section_path: str
    category: str
    kinds: set[str] = field(default_factory=set)
    rerank_applied: bool = False


@dataclass
class SearchResult:
    """检索结果集合（含可观测信息）。"""

    hits: list[SearchHit]
    query: str
    tenant_id: str
    vector_hits: int
    parent_count: int
    rerank_applied: bool
    elapsed_ms: int


# 全局单例（服务运行时复用连接与模型）
_store = None
_rerank_model = None
_rerank_tried = False


def _get_store():
    """惰性构建 Milvus 连接。"""
    global _store
    if _store is None:
        from app.core.config import vector_store_config as cfg
        from rag.store import VectorStore

        uri = cfg.uri or f"http://{cfg.host}:{cfg.port}"
        _store = VectorStore(
            uri=uri, collection=cfg.collection,
            dim=cfg.dims, metric_type=cfg.metric_type,
        )
    return _store


def _get_rerank_model():
    """惰性构建 Rerank 模型；未配置则返回 None（降级为不精排）。"""
    global _rerank_model, _rerank_tried
    if _rerank_tried:
        return _rerank_model
    _rerank_tried = True
    try:
        from app.core.config import rerank_config

        if not rerank_config.is_valid:
            return None
        from rag.rerank.ark_rerank import ArkRerankModel

        _rerank_model = ArkRerankModel(
            api_key=rerank_config.api_key,
            base_url=rerank_config.base_url,
            model=rerank_config.model,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rerank 初始化失败，降级为不精排: %s", exc)
        _rerank_model = None
    return _rerank_model


async def _embed_query(query: str) -> list[float]:
    """把查询向量化。"""
    from agentscope.message import TextBlock

    from app.embedding import build_embedding_model

    model = build_embedding_model()
    resp = await model([TextBlock(text=query)])
    return resp.embeddings[0]


async def search(
    query: str,
    *,
    tenant_id: str = "default",
    roles: set[str] | None = None,
    top_k: int = 5,
    fetch_k: int = 30,
    enable_rerank: bool = True,
    vector_weight: float = 1.0,
    keyword_weight: float = 1.0,
) -> SearchResult:
    """执行混合检索并返回父块级结果。

    Args:
        query: 用户查询。
        tenant_id: 租户 ID（Milvus 侧硬过滤）。
        roles: 用户角色集合，用于权限过滤（None 仅看 public）。
        top_k: 最终返回父块数。
        fetch_k: 向量召回子块数（留足融合与精排空间）。
        enable_rerank: 是否启用 Rerank 精排。
        vector_weight: 向量通道融合权重。
        keyword_weight: 关键词通道融合权重。

    Returns:
        SearchResult。
    """
    import time

    start = time.time()

    # 1) 向量召回子块（租户硬过滤在 Milvus 侧完成）
    query_vector = await _embed_query(query)
    store = _get_store()
    vec_rows = store.search(query_vector, top_k=fetch_k, tenant_id=tenant_id)

    # 权限过滤（public 或角色匹配）
    def _visible(row: dict) -> bool:
        perm = row.get("permission", "public")
        if perm == "public":
            return True
        return bool(roles) and perm in roles

    rows = {r["record_id"]: r for r in vec_rows if _visible(r)}
    if not rows:
        return SearchResult(
            hits=[], query=query, tenant_id=tenant_id, vector_hits=len(vec_rows),
            parent_count=0, rerank_applied=False,
            elapsed_ms=int((time.time() - start) * 1000),
        )

    vector_ranking = [rid for rid in rows]  # Milvus 已按相似度排序

    # 2) BM25 关键词通道（在召回子块上打分）
    kw = KeywordIndex()
    for rid, row in rows.items():
        kw.add(rid, row.get("text", ""))
    kw.build()
    keyword_ranking = [rid for rid, _ in kw.search(query, top_k=len(rows))]

    # 3) RRF 融合子块排名
    fused = reciprocal_rank_fusion(
        [vector_ranking, keyword_ranking],
        weights=[vector_weight, keyword_weight],
    )

    # 4) 父块聚合：同一父块取最高分子块
    parent_best: dict[str, tuple[float, dict]] = {}
    parent_kinds: dict[str, set[str]] = {}
    for rid, score in fused:
        row = rows[rid]
        pid = row.get("parent_id", rid)
        parent_kinds.setdefault(pid, set()).add(row.get("kind", "text"))
        if pid not in parent_best or score > parent_best[pid][0]:
            parent_best[pid] = (score, row)

    # 5) 归一化 + 型号/类型加权
    ordered = sorted(parent_best.items(), key=lambda kv: kv[1][0], reverse=True)
    max_score = ordered[0][1][0] or 1.0
    normalized = [(pid, sc / max_score) for pid, (sc, _r) in ordered]
    kinds_of = {pid: parent_kinds[pid] for pid, _ in normalized}
    text_of = {pid: parent_best[pid][1].get("parent_text", "") for pid, _ in normalized}
    boosted = apply_boosts(query, normalized, kinds_of, text_of)

    # 组装父块候选（精排前多留一些）
    candidates: list[SearchHit] = []
    for pid, score in boosted[: max(top_k * 2, top_k)]:
        _sc, row = parent_best[pid]
        candidates.append(
            SearchHit(
                parent_id=pid,
                text=row.get("parent_text", ""),
                matched_text=row.get("text", ""),
                score=score,
                filename=row.get("filename", "unknown"),
                section_path=row.get("section_path", ""),
                category=row.get("category", "general"),
                kinds=parent_kinds[pid],
            ),
        )

    # 6) Rerank 精排（可选，失败自动降级）
    rerank_applied = False
    if enable_rerank and len(candidates) > 1:
        model = _get_rerank_model()
        if model is not None:
            try:
                results = await model.rerank(
                    query, [c.text for c in candidates], top_n=top_k,
                )
                reranked = []
                for r in results:
                    hit = candidates[r.index]
                    hit.score = r.score
                    hit.rerank_applied = True
                    reranked.append(hit)
                candidates = reranked
                rerank_applied = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Rerank 调用失败，使用融合排序: %s", exc)

    hits = candidates[:top_k]
    return SearchResult(
        hits=hits,
        query=query,
        tenant_id=tenant_id,
        vector_hits=len(vec_rows),
        parent_count=len(parent_best),
        rerank_applied=rerank_applied,
        elapsed_ms=int((time.time() - start) * 1000),
    )
