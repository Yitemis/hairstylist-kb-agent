# -*- coding: utf-8 -*-
"""Milvus 向量存储层（子块级，显式 Schema）。

以子块（父子分块中的"子"）为存储粒度，采用显式字段 Schema，使每条记录在
Milvus 面板（Attu）中都可读：文本、父块全文、章节、内容形态、型号、租户、
权限等一目了然，而非仅一团向量。

字段设计对齐 :class:`rag.pipeline.IndexRecord`：

* ``vector``       子块向量（检索用）
* ``text``         子块文本（BM25 / 展示）
* ``parent_text``  父块全文（命中后作上下文返回）
* ``tenant_id`` / ``permission``  多租户与权限硬过滤
* ``section_path`` / ``kind`` / ``models``  章节、形态、型号（加权与定向召回）

检索侧提供向量搜索接口，返回按相似度排序的子块 record_id，交由 pipeline 做
父块聚合与混合检索。
"""
from __future__ import annotations

import logging
from typing import Any

from pymilvus import DataType, MilvusClient

logger = logging.getLogger(__name__)

# 变长字段的最大字符容量（Milvus VARCHAR 上限，父块文本给足空间）
_MAX_TEXT = 8192
_MAX_PARENT_TEXT = 16384
_MAX_ID = 256
_MAX_SHORT = 512


class VectorStore:
    """Milvus 子块向量库封装。"""

    def __init__(
        self,
        uri: str,
        collection: str,
        dim: int,
        metric_type: str = "COSINE",
    ) -> None:
        """连接 Milvus 并确保集合存在。

        Args:
            uri: Milvus 服务地址，如 ``http://127.0.0.1:19530``。
            collection: 集合名。
            dim: 向量维度（需与 embedding 输出一致）。
            metric_type: 距离度量，余弦相似度默认。
        """
        self.client = MilvusClient(uri=uri)
        self.collection = collection
        self.dim = dim
        self.metric_type = metric_type
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """集合不存在则按显式 Schema 创建，并建向量索引。"""
        if self.client.has_collection(self.collection):
            logger.info("向量集合已存在: %s", self.collection)
            self.client.load_collection(self.collection)
            return

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("record_id", DataType.VARCHAR, is_primary=True, max_length=_MAX_ID)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.dim)
        schema.add_field("text", DataType.VARCHAR, max_length=_MAX_TEXT)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=_MAX_ID)
        schema.add_field("parent_text", DataType.VARCHAR, max_length=_MAX_PARENT_TEXT)
        schema.add_field("tenant_id", DataType.VARCHAR, max_length=_MAX_ID)
        schema.add_field("permission", DataType.VARCHAR, max_length=_MAX_SHORT)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=_MAX_ID)
        schema.add_field("filename", DataType.VARCHAR, max_length=_MAX_SHORT)
        schema.add_field("category", DataType.VARCHAR, max_length=_MAX_SHORT)
        schema.add_field("section_path", DataType.VARCHAR, max_length=_MAX_SHORT)
        schema.add_field("kind", DataType.VARCHAR, max_length=64)
        schema.add_field("models", DataType.VARCHAR, max_length=_MAX_SHORT)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type=self.metric_type,
        )

        self.client.create_collection(
            collection_name=self.collection,
            schema=schema,
            index_params=index_params,
        )
        logger.info("已创建向量集合: %s (dim=%d)", self.collection, self.dim)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def upsert(self, rows: list[dict[str, Any]]) -> int:
        """批量写入（存在则覆盖）。每行需含 ``vector`` 与各标量字段。"""
        if not rows:
            return 0
        self.client.upsert(collection_name=self.collection, data=rows)
        return len(rows)

    def delete_by_doc(self, tenant_id: str, doc_id: str) -> None:
        """删除某租户下某文档的全部子块（重建索引前清理用）。"""
        expr = f'tenant_id == "{tenant_id}" and doc_id == "{doc_id}"'
        self.client.delete(collection_name=self.collection, filter=expr)

    def clear(self) -> None:
        """清空并重建集合。"""
        if self.client.has_collection(self.collection):
            self.client.drop_collection(self.collection)
        self._ensure_collection()

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        top_k: int = 20,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """向量检索，返回命中子块的字段字典列表（按相似度降序）。

        Args:
            query_vector: 查询向量。
            top_k: 召回数量。
            tenant_id: 指定则在 Milvus 侧做租户硬过滤。

        Returns:
            每项含 record_id / text / parent_id / parent_text / section_path /
            kind / models / score 等字段。
        """
        expr = f'tenant_id == "{tenant_id}"' if tenant_id else None
        output_fields = [
            "record_id", "text", "parent_id", "parent_text", "tenant_id",
            "permission", "doc_id", "filename", "category", "section_path",
            "kind", "models",
        ]
        results = self.client.search(
            collection_name=self.collection,
            data=[query_vector],
            limit=top_k,
            filter=expr or "",
            output_fields=output_fields,
        )
        hits: list[dict[str, Any]] = []
        for hit in results[0]:
            entity = dict(hit.get("entity", {}))
            entity["score"] = hit.get("distance")
            hits.append(entity)
        return hits

    def count(self, tenant_id: str | None = None) -> int:
        """统计记录数（可按租户）。"""
        expr = f'tenant_id == "{tenant_id}"' if tenant_id else ""
        res = self.client.query(
            collection_name=self.collection,
            filter=expr,
            output_fields=["record_id"],
            limit=16384,
        )
        return len(res)
