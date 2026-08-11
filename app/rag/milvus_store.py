# -*- coding: utf-8 -*-
"""Milvus 向量库适配器（pymilvus 2.x）。

参考 ekbs 设计：
- 集合 schema: id, vector, parent_id, tenant_id, document_id, filename, category
- 只存子块（不含父块全文）
- 父块文本存业务库（ParentChunk 表），通过 parent_id 关联
- 检索：向量召回子块 -> 批量查业务库拿父块

依赖: pip install pymilvus
"""
from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# 字段名常量（跨模块引用）
PARENT_ID_KEY = "parent_id"
TENANT_ID_KEY = "tenant_id"
DOCUMENT_ID_KEY = "document_id"
FILENAME_KEY = "filename"
CATEGORY_KEY = "category"
AUDIENCE_KEY = "audience"
IS_PUBLISHED_KEY = "is_published"


class MilvusStore:
    """Milvus 2.x 适配器（生产级，独立于 AgentScope wrapper）。"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection: str = "hairstylist_kb",
        dim: int = 1024,
        metric_type: str = "COSINE",
    ):
        self.host = host
        self.port = port
        self.collection = collection
        self.dim = dim
        self.metric_type = metric_type
        self._client: Optional[Any] = None

    def _get_client(self):
        """懒加载 pymilvus client。"""
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as e:
                raise ImportError("请先 pip install pymilvus") from e
            self._client = MilvusClient(uri=f"http://{self.host}:{self.port}")
            logger.info("Milvus 连接: %s:%d", self.host, self.port)
        return self._client

    def ensure_collection(self) -> None:
        """确保集合存在（按 dim 建 HNSW 索引）。"""
        client = self._get_client()
        if client.has_collection(self.collection):
            logger.info("Milvus 集合已存在: %s", self.collection)
            return
        client.create_collection(
            collection_name=self.collection,
            dimension=self.dim,
            metric_type=self.metric_type,
            auto_id=True,
        )
        # 建 HNSW 索引（生产推荐）
        # pymilvus 2.x: create_collection 已经建了默认 AUTOINDEX
        # 再 create_index 会冲突，所以只建一次
        # 已用 metric_type 指定距离，建索引由 Milvus 自动管理
        logger.info("Milvus 集合创建: %s (dim=%d, metric=%s)", self.collection, self.dim, self.metric_type)

    def insert(self, vectors: List[List[float]], payloads: List[dict]) -> List[int]:
        """插入子块（payload 必含 parent_id / tenant_id / document_id / filename）。"""
        self.ensure_collection()
        client = self._get_client()
        data = []
        for vec, p in zip(vectors, payloads):
            # auto_id=True 时 Milvus 自动分配 id
            row = {"vector": vec}
            row.update({
                PARENT_ID_KEY: str(p.get(PARENT_ID_KEY, "")),
                TENANT_ID_KEY: str(p.get(TENANT_ID_KEY, "default")),
                DOCUMENT_ID_KEY: str(p.get(DOCUMENT_ID_KEY, "")),
                FILENAME_KEY: str(p.get(FILENAME_KEY, "")),
                CATEGORY_KEY: str(p.get(CATEGORY_KEY, "general")),
                AUDIENCE_KEY: str(p.get(AUDIENCE_KEY, "all")),
                IS_PUBLISHED_KEY: bool(p.get(IS_PUBLISHED_KEY, False)),
            })
            data.append(row)
        result = client.insert(collection_name=self.collection, data=data)
        ids = result.get("ids", []) if isinstance(result, dict) else getattr(result, "ids", [])
        logger.info("Milvus 插入: %d 子块", len(data))
        return ids

    def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        top_k: int = 20,
        category_filter: Optional[List[str]] = None,
        document_id_filter: Optional[str] = None,
        audience_filter: Optional[List[str]] = None,
        include_unpublished: bool = False,
    ) -> List[dict]:
        """向量检索（多租户隔离）。返回 [{id, score, payload}, ...]

        Filter 表达式：
        - Milvus 用双引号包裹字符串字面量
        - list 字段用 `in ["a", "b"]`
        - boolean 字段用 `== true` / `== false`
        """
        client = self._get_client()
        # 安全转义：双引号 → 反斜杠转义
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        # 构造过滤表达式
        filter_parts = [f'{TENANT_ID_KEY} == "{_esc(tenant_id)}"']
        if category_filter:
            cats = '", "'.join(_esc(c) for c in category_filter)
            filter_parts.append(f'{CATEGORY_KEY} in ["{cats}"]')
        if audience_filter:
            auds = '", "'.join(_esc(a) for a in audience_filter)
            filter_parts.append(f'{AUDIENCE_KEY} in ["{auds}"]')
        if not include_unpublished:
            filter_parts.append(f'{IS_PUBLISHED_KEY} == true')
        if document_id_filter:
            filter_parts.append(f'{DOCUMENT_ID_KEY} == "{_esc(document_id_filter)}"')
        filter_expr = " and ".join(filter_parts)
        results = client.search(
            collection_name=self.collection,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=[
                PARENT_ID_KEY, TENANT_ID_KEY, DOCUMENT_ID_KEY,
                FILENAME_KEY, CATEGORY_KEY, AUDIENCE_KEY,
            ],
        )
        # 格式标准化
        hits = []
        for r in results[0]:
            entity = r.get("entity", {}) or {}
            hits.append({
                "id": r.get("id"),
                "score": r.get("distance", 0.0),
                "parent_id": entity.get(PARENT_ID_KEY, ""),
                "tenant_id": entity.get(TENANT_ID_KEY, ""),
                "document_id": entity.get(DOCUMENT_ID_KEY, ""),
                "filename": entity.get(FILENAME_KEY, "unknown"),
                "category": entity.get(CATEGORY_KEY, "general"),
                "audience": entity.get(AUDIENCE_KEY, "all"),
            })
        return hits

    def delete_by_document(self, document_id: str, tenant_id: str) -> int:
        """按 document_id 删除（用于更新）。"""
        client = self._get_client()
        result = client.delete(
            collection_name=self.collection,
            filter=f'{DOCUMENT_ID_KEY} == "{document_id}" and {TENANT_ID_KEY} == "{tenant_id}"',
        )
        count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        logger.info("Milvus 删除文档 %s: %d 子块", document_id, count)
        return count

    def count(self, tenant_id: Optional[str] = None) -> int:
        """统计子块数。"""
        client = self._get_client()
        if tenant_id:
            result = client.query(
                collection_name=self.collection,
                filter=f'{TENANT_ID_KEY} == "{tenant_id}"',
                output_fields=["id"],
            )
            return len(result)
        stats = client.get_collection_stats(self.collection)
        return stats.get("row_count", 0)
