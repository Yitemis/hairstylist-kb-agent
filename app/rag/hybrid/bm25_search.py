# -*- coding: utf-8 -*-
"""BM25 全文检索（基于 PostgreSQL tsvector + ts_rank）。

设计：
- 用 PG 原生全文搜索（生产级，性能 + 准确率都 OK）
- 中文分词：jieba（客户端分好再传 PG）
- BM25-like 排序：ts_rank_cd (PostgreSQL 自带，BM25 风格)
- 多租户隔离：filter 表达式

借鉴 12-factor app：检索层用 PG 复用现有基础设施（不用 ES / Redis）。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# 缓存 jieba 导入
_jieba = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba
            _jieba = jieba
        except ImportError:
            logger.warning("jieba 未安装，fallback 到字符切分（pip install jieba）")
            _jieba = None
    return _jieba


def tokenize_chinese(text: str) -> str:
    """中文分词 -> PG tsquery 格式。

    PG `to_tsquery` 需要 & | ! () 操作符连接 tokens。
    输出格式: 'token1 & token2 & token3'
    """
    text = re.sub(r'[^\w一-鿿]+', ' ', text).strip()
    if not text:
        return ""

    jieba = _get_jieba()
    if jieba is not None:
        tokens = [t for t in jieba.cut(text) if len(t.strip()) > 1]
    else:
        # Fallback: 字符切分（中文按字 + 英文按词）
        tokens = []
        for part in re.findall(r'[一-鿿]|[a-zA-Z]+|\d+', text):
            if len(part) == 1 and re.match(r'[一-鿿]', part):
                tokens.append(part)  # 单字
            elif len(part) > 1:
                tokens.append(part)

    # 转义 PG tsquery 特殊字符
    safe_tokens = []
    for t in tokens:
        t_clean = re.sub(r'[&|!()\s]', '', t).strip()
        if t_clean:
            safe_tokens.append(t_clean)

    return " & ".join(safe_tokens) if safe_tokens else ""


def update_parent_chunk_tsv(conn, parent_id: str, content: str) -> None:
    """更新 parent_chunk 的 tsvector 列。

    借鉴 PG 触发器模式：插入/更新时自动生成 tsvector。
    这里我们手动调用（避免每次入库写触发器）。
    """
    # 用 'simple' 配置（不做词形还原）+ 'public.chinese_zh' 兜底
    # 客户端先分词，存到 tsvector（不用 PG 端分词）
    from sqlalchemy import text
    conn.execute(
        text("""
            UPDATE parent_chunks
            SET content_tsv = to_tsvector('simple', :content)
            WHERE parent_id = :pid
        """),
        {"content": content, "pid": parent_id},
    )


async def bm25_search(
    session_maker,
    query: str,
    tenant_id: str,
    top_k: int = 20,
    category_filter: Optional[List[str]] = None,
) -> List[dict]:
    """BM25 全文检索（PG tsvector + ts_rank_cd）。

    Returns:
        [{parent_id, score, content, document_id, filename}, ...]
    """
    from sqlalchemy import text

    # 客户端分词
    tsquery_str = tokenize_chinese(query)
    if not tsquery_str:
        logger.warning("BM25: 查询分词后为空")
        return []

    # category filter
    cat_filter = ""
    if category_filter:
        cats = "', '".join(category_filter)
        cat_filter = f"AND d.category IN ('{cats}')"

    # SQL: ts_rank_cd (BM25-style ranking, takes position into account)
    sql = f"""
        SELECT
            pc.parent_id,
            pc.content,
            pc.document_id,
            d.filename,
            ts_rank_cd(pc.content_tsv, to_tsquery('simple', :tsquery)) AS rank
        FROM parent_chunks pc
        JOIN documents d ON d.document_id = pc.document_id
        WHERE pc.tenant_id = :tenant_id
          AND pc.content_tsv @@ to_tsquery('simple', :tsquery)
          {cat_filter}
        ORDER BY rank DESC
        LIMIT :top_k
    """

    async with session_maker() as session:
        result = await session.execute(
            text(sql),
            {
                "tsquery": tsquery_str,
                "tenant_id": tenant_id,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

    return [
        {
            "parent_id": r.parent_id,
            "content": r.content,
            "document_id": r.document_id,
            "filename": r.filename,
            "score": float(r.rank),
        }
        for r in rows
    ]


def rrf_fuse(
    vector_hits: List[dict],
    bm25_hits: List[dict],
    k: int = 60,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> List[dict]:
    """RRF (Reciprocal Rank Fusion) 融合双路召回。

    公式: score(d) = sum(weight_i / (k + rank_i))
    - k 通常 60 (原 RRF 论文)
    - vector_weight + bm25_weight 不必 = 1（融合后排序只看相对值）
    """
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    # Vector 召回
    for rank, hit in enumerate(vector_hits, 1):
        pid = hit["parent_id"]
        scores[pid] = scores.get(pid, 0) + vector_weight / (k + rank)
        payloads[pid] = hit

    # BM25 召回
    for rank, hit in enumerate(bm25_hits, 1):
        pid = hit["parent_id"]
        scores[pid] = scores.get(pid, 0) + bm25_weight / (k + rank)
        # BM25 hit 已有 content（DB 拿的）
        if pid not in payloads:
            payloads[pid] = hit
        else:
            # 合并：BM25 的 content 更准确（从 DB）
            payloads[pid]["content"] = hit.get("content", payloads[pid].get("content", ""))
            payloads[pid]["filename"] = hit.get("filename", payloads[pid].get("filename", ""))

    # 按 RRF score 排序
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**payloads[pid], "score": score}
        for pid, score in fused
    ]
