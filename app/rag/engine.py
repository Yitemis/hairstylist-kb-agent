# -*- coding: utf-8 -*-
"""RAG 引擎：多租户隔离 + Self-RAG 两阶段检索。

核心能力：
1. 多租户隔离：按 tenant_id 过滤检索，SaaS 部署安全
2. 父子分块检索：子块向量召回 -> 父块完整上下文还原
3. Self-RAG 自主反思：Agent 判断检索质量，不够则自动重试
4. 可审计：检索耗时、命中数、分数，接入监控面板
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any



from app.core.config import vector_store_config
from app.embedding import build_embedding_model
from rag.chunkers.parent_child_chunker import (
    PARENT_CONTENT_KEY,
    PARENT_ID_KEY,
    ParentChildChunker,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    """单次检索命中结果（父块级）。"""
    parent_id: str
    content: str
    source: str
    score: float
    matched_child: str
    tenant_id: str


@dataclass
class RetrievalResult:
    """完整检索结果（含审计信息）。"""
    hits: list[RetrievalHit]
    retrieval_time_ms: int
    child_hits_count: int
    parent_count: int
    rerank_applied: bool
    tenant_id: str


def _convert_search_result(r) -> dict:
    """把 AgentScope VectorSearchResult 转成 dict 兼容旧代码。

    AgentScope 的 VectorSearchResult 字段：
    - score: float
    - chunk.content.text: str
    - chunk.source: str
    - chunk.metadata: dict
    """
    try:
        return {
            "score": r.score,
            "payload": r.chunk.metadata or {},
            # 提取父块 ID 用于聚合
            "parent_id": (r.chunk.metadata or {}).get(PARENT_ID_KEY, ""),
            # 父块内容（如有）
            "content": (r.chunk.metadata or {}).get(PARENT_CONTENT_KEY, ""),
            "filename": (r.chunk.metadata or {}).get("filename", "unknown"),
        }
    except Exception:
        return {"score": 0.0, "payload": {}, "parent_id": "", "content": "", "filename": "unknown"}


_vector_store = None
_qdrant_direct_client = None  # qdrant-local 直接 client（避开 AgentScope wrapper 的 path bug）
_chunker = ParentChildChunker()


async def _get_vector_store():
    """获取向量库实例（懒加载 + 自动建集合）。

    引擎支持：
    - milvus（默认，Docker 启动，带可视化面板）
    - qdrant-local（本地文件快速开发）
    """
    global _vector_store, _qdrant_direct_client
    if _vector_store is None:
        engine = vector_store_config.engine

        if engine == "milvus":
            from agentscope.rag import MilvusLiteStore
            uri = vector_store_config.uri or f"http://{vector_store_config.host}:{vector_store_config.port}"
            logger.info("初始化 Milvus 向量库: %s", uri)
            _vector_store = MilvusLiteStore(uri=uri)
        else:
            # qdrant-local：直接用 QdrantClient 连本地文件，避开 AgentScope wrapper bug
            from qdrant_client import AsyncQdrantClient
            from agentscope.rag import QdrantStore
            _vector_store = QdrantStore(location=vector_store_config.path)
            logger.info("初始化 Qdrant 本地向量库: %s", vector_store_config.path)
            # 直接初始化一个 AsyncQdrantClient
            _qdrant_direct_client = AsyncQdrantClient(
                path=vector_store_config.path,
            )
            # 检查/创建集合
            try:
                await _qdrant_direct_client.get_collection(vector_store_config.collection)
                logger.info("Qdrant 集合已存在: %s", vector_store_config.collection)
            except Exception:
                from qdrant_client import models as qdrant_models
                await _qdrant_direct_client.create_collection(
                    collection_name=vector_store_config.collection,
                    vectors_config=qdrant_models.VectorParams(
                        size=vector_store_config.dims,
                        distance=qdrant_models.Distance.COSINE,
                    ),
                )
                logger.info("Qdrant 创建集合: %s (维度: %d)",
                            vector_store_config.collection, vector_store_config.dims)

    return _vector_store


async def _get_qdrant_client():
    """获取 Qdrant 直连 client（qdrant-local 模式专用）。"""
    global _qdrant_direct_client
    if _qdrant_direct_client is None:
        await _get_vector_store()  # 触发初始化
    return _qdrant_direct_client

async def index_document(
    document_id: str,
    content: str,
    filename: str,
    tenant_id: str = "default",
    category: str = "general",
) -> dict[str, Any]:
    """多租户文档索引：解析 -> 父子分块 -> 嵌入 -> 入库。

    Args:
        document_id: 文档唯一ID
        content: 文档正文
        filename: 来源文件名（用于引用溯源）
        tenant_id: 租户ID（SaaS隔离用）
        category: 文档分类（如 洗护产品/染烫技术/服务话术）
    """
    start_time = time.time()

    from agentscope.message import TextBlock
    from agentscope.rag._document import Section

    section = Section(
        content=TextBlock(text=content),
        source=filename,
        metadata={
            "document_id": document_id,
            "tenant_id": tenant_id,
            "category": category,
        },
    )

    chunks = await _chunker.chunk([section])
    logger.info("文档 %s 分块完成: %d 个子块", document_id, len(chunks))

    embed_model = build_embedding_model()
    texts = [c.content.text for c in chunks if hasattr(c.content, "text")]

    if not texts:
        return {"status": "empty", "chunks": 0, "time_ms": 0}

    embed_resp = await embed_model([TextBlock(text=t) for t in texts])
    vectors = embed_resp.embeddings  # AgentScope 2.0 字段名是 embeddings（复数）

    points = []
    for idx, chunk in enumerate(chunks):
        if not hasattr(chunk.content, "text"):
            continue

        meta = dict(chunk.metadata or {})
        meta["tenant_id"] = tenant_id
        meta["document_id"] = document_id
        meta["filename"] = filename
        meta["category"] = category

        points.append({
            "id": hash(f"{tenant_id}:{document_id}:{idx}"),
            "vector": vectors[idx],
            "payload": meta,
        })

    vs = await _get_vector_store()
    if vector_store_config.engine == "qdrant-local":
        # qdrant-local 用直连 client（避开 AgentScope wrapper 的 path bug）
        from qdrant_client import models as qdrant_models
        client = await _get_qdrant_client()
        # 转换 dict 为 PointStruct
        qdrant_points = [
            qdrant_models.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        await client.upsert(
            collection_name=vector_store_config.collection,
            points=qdrant_points,
        )
    else:
        async with vs:
            await vs._client.upsert(  # milvus
                collection_name=vector_store_config.collection,
                points=points,
            )

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info("文档 %s 索引完成: %d 子块, %dms", document_id, len(points), elapsed_ms)

    return {
        "status": "ok",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "chunks_indexed": len(points),
        "time_ms": elapsed_ms,
    }

async def retrieve(
    query: str,
    tenant_id: str = "default",
    top_k: int = 5,
    fetch_k: int = 20,
    enable_rerank: bool = True,
    category_filter: list[str] | None = None,
) -> RetrievalResult:
    """两阶段检索（多租户隔离）。

    阶段1：向量粗召回子块 Top-FetchK
    阶段2：按父块 ID 聚合去重 -> Rerank 精排 -> 返回 Top-K 父块
    强制携带 tenant_id 过滤，保证多租户数据隔离。
    """
    start_time = time.time()

    from agentscope.message import TextBlock

    embed_model = build_embedding_model()
    query_resp = await embed_model([TextBlock(text=query)])
    query_vector = query_resp.embeddings[0]  # AgentScope 2.0 字段名是 embeddings（复数）

    engine_type = vector_store_config.engine
    vs = await _get_vector_store()

    # 不同向量库的 filter 格式不同
    if engine_type == "qdrant-local":
        # Qdrant 用 qdrant_client.models.Filter
        from qdrant_client import models as qdrant_models
        must_conditions = [
            qdrant_models.FieldCondition(
                key="tenant_id",
                match=qdrant_models.MatchValue(value=tenant_id),
            )
        ]
        if category_filter:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="category",
                    match=qdrant_models.MatchAny(any=category_filter),
                )
            )
        metadata_filter = qdrant_models.Filter(must=must_conditions)
    elif engine_type == "milvus":
        # Milvus 用 filter 表达式字符串
        filter_expr = f'tenant_id == "{tenant_id}"'
        if category_filter:
            cats = '", "'.join(category_filter)
            filter_expr += f' AND category IN ["{cats}"]'
        metadata_filter = filter_expr
    else:
        metadata_filter = None

    # AgentScope 2.0 的 QdrantStore.search 直接接收 metadata_filter
    # Qdrant 本地模式：AgentScope wrapper 与 Qdrant 1.x Filter 兼容性问题，直接用底层 client
    if engine_type == "qdrant-local":
        # qdrant-local 用直连 client
        client = await _get_qdrant_client()
        qdrant_resp = await client.query_points(
            collection_name=vector_store_config.collection,
            query=query_vector,
            limit=fetch_k,
            with_payload=True,
            with_vectors=False,
            query_filter=metadata_filter,
        )
        results = qdrant_resp.points  # ScoredPoint 列表
        # 把 ScoredPoint 转成 dict 兼容
        results = [
            {
                "score": r.score,
                "payload": r.payload or {},
                "parent_id": (r.payload or {}).get(PARENT_ID_KEY, ""),
                "content": (r.payload or {}).get(PARENT_CONTENT_KEY, ""),
                "filename": (r.payload or {}).get("filename", "unknown"),
            }
            for r in results
        ]
    else:  # milvus
        async with vs:
            raw_results = await vs.search(
                collection=vector_store_config.collection,
                query_vector=query_vector,
                top_k=fetch_k,
                metadata_filter=metadata_filter,
            )
            results = [_convert_search_result(r) for r in raw_results]

    child_hits_count = len(results)
    logger.info("向量召回: %d 子块命中 (tenant=%s)", child_hits_count, tenant_id)

    best_by_parent: dict[str, RetrievalHit] = {}
    for hit in results:
        # results 在 qdrant-local 模式是 dict（直接构造的）
        # 在 milvus 模式是 dict（_convert_search_result 转的）
        # 统一用 .get("payload", {}) 兼容
        if isinstance(hit, dict):
            payload = hit.get("payload", {})
            score = hit.get("score", 0.0)
        else:
            payload = getattr(hit, "payload", None) or {}
            score = getattr(hit, "score", 0.0)
        parent_id = payload.get(PARENT_ID_KEY)
        if not parent_id:
            continue

        if parent_id not in best_by_parent or score > best_by_parent[parent_id].score:
            best_by_parent[parent_id] = RetrievalHit(
                parent_id=parent_id,
                content=payload.get(PARENT_CONTENT_KEY, ""),
                source=payload.get("filename", "unknown"),
                score=score,
                matched_child="",
                tenant_id=tenant_id,
            )

    parent_hits = sorted(best_by_parent.values(), key=lambda h: h.score, reverse=True)[:top_k*2]
    rerank_applied = False

    if enable_rerank and len(parent_hits) > 1:
        try:
            from app.embedding import build_rerank_model
            from agentscope.message import TextBlock

            rerank_model = build_rerank_model()
            # 构造 query + doc 对，rerank 模型打分
            pairs = [
                [query, hit.content[:500]] for hit in parent_hits
            ]
            scores_resp = await rerank_model(pairs)
            for hit, score in zip(parent_hits, scores_resp.scores):
                hit.score = float(score)
            parent_hits.sort(key=lambda h: h.score, reverse=True)
            rerank_applied = True
            logger.info("Rerank 完成: %d 文档", len(parent_hits))
        except Exception as e:
            logger.warning("Rerank 失败，回退到向量分数: %s", e)

    final_hits = parent_hits[:top_k]
    elapsed_ms = int((time.time() - start_time) * 1000)

    return RetrievalResult(
        hits=final_hits,
        retrieval_time_ms=elapsed_ms,
        child_hits_count=child_hits_count,
        parent_count=len(parent_hits),
        rerank_applied=rerank_applied,
        tenant_id=tenant_id,
    )


async def self_rag_retrieve(
    query: str,
    tenant_id: str = "default",
    top_k: int = 5,
    max_retries: int = 2,
    min_score_threshold: float = 0.5,
) -> RetrievalResult:
    """Self-RAG 检索：Agent 自主判断检索质量，不够则自动重试优化。

    反思逻辑：
    1. 无检索结果 -> 加领域关键词重试
    2. 最高分 < 阈值 -> 加领域限定词重试
    3. 命中数 < 2 -> 扩大召回范围重试
    最多重试 max_retries 次。
    """
    best_result = None
    attempts = 0

    while attempts < max_retries + 1:
        result = await retrieve(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            fetch_k=top_k * 4,
        )

        if best_result is None or (result.hits and result.hits[0].score > best_result.hits[0].score):
            best_result = result

        if not result.hits:
            logger.warning("无检索结果，第 %d 次重试 (tenant=%s)", attempts, tenant_id)
            query = f"{query} 美发 专业知识"
            attempts += 1
            continue

        top_score = result.hits[0].score
        hit_count = len(result.hits)

        if top_score >= min_score_threshold and hit_count >= 2:
            logger.info(
                "Self-RAG 质量达标: 最高分数 %.3f, 命中 %d 个父块",
                top_score, hit_count,
            )
            return result

        if top_score < min_score_threshold:
            logger.warning("检索质量不足 (%.2f < %.2f)，优化查询重试", top_score, min_score_threshold)
            query = f"美发行业 {query} 专业说明"
        elif hit_count < 2:
            logger.warning("命中太少 (%d < 2)，扩大召回重试", hit_count)
            top_k *= 2

        attempts += 1
        await asyncio.sleep(0.1)

    logger.warning("已达最大重试次数，返回最佳结果")
    return best_result or RetrievalResult(
        hits=[], retrieval_time_ms=0, child_hits_count=0,
        parent_count=0, rerank_applied=False, tenant_id=tenant_id,
    )


async def get_knowledge_stats(tenant_id: str | None = None) -> dict[str, Any]:
    """获取知识库统计信息（监控面板用）。"""
    try:
        if vector_store_config.engine == "qdrant-local":
            client = await _get_qdrant_client()
            count_resp = await client.count(collection_name=vector_store_config.collection)
            total = count_resp.count
        else:
            vs = await _get_vector_store()
            async with vs:
                count = await vs._client.count(collection_name=vector_store_config.collection)
                total = count.count
        return {"total_chunks": total, "tenant_filtered": tenant_id}
    except Exception as e:
        logger.warning("get_knowledge_stats 失败: %s", e)
        return {"total_chunks": 0, "tenant_filtered": tenant_id, "error": str(e)}