# -*- coding: utf-8 -*-
"""ParentChildKnowledgeBase —— 父子感知的知识库（M3 核心）。

在框架 KnowledgeBase 的基础上，实现"检索命中子块 → 返回父块完整原文"的逻辑。

【为什么要自定义 search】
框架的 KnowledgeBase.search 返回的是命中的【子块】本身。但父子分块的价值在于：
用子块做精准检索，却要把【父块完整原文】喂给 LLM。所以我们在框架 search 之上
再包一层：命中子块后，从子块 metadata 里取出父块内容，并按父块去重。

【组合而非继承】
这里采用"组合"框架 KnowledgeBase 的方式（内部持有一个 KnowledgeBase 实例），
而不是继承。原因：框架 KnowledgeBase 的 search 签名/去重逻辑较复杂，组合能让
我们的父子逻辑更清晰、边界更明确，也更符合"单一职责"。
"""
from dataclasses import dataclass

from agentscope.embedding import EmbeddingModelBase
from agentscope.message import DataBlock, TextBlock
from agentscope.rag import KnowledgeBase
from agentscope.rag._document import Chunk
from agentscope.rag._vdb import VectorStoreBase

from .chunkers.parent_child_chunker import (
    PARENT_CONTENT_KEY,
    PARENT_ID_KEY,
    PARENT_INDEX_KEY,
)
from .rerank.base import RerankModelBase


@dataclass
class ParentHit:
    """一次父子检索的命中结果（已还原为父块）。"""

    parent_id: str
    """父块唯一 ID。"""
    content: str
    """父块完整原文（喂给 LLM 的内容）。"""
    source: str
    """来源文件名（用于引用标注）。"""
    score: float
    """命中该父块的最佳子块的相似度分数。"""
    matched_child: str
    """实际命中的子块文本（便于调试/展示"为什么召回了这个父块"）。"""


class ParentChildKnowledgeBase:
    """父子感知知识库。

    索引侧：用 ParentChildChunker 切出的子块（带父块 metadata）灌入向量库。
    检索侧：子块向量召回 → 还原父块 → 按父块去重 → 返回父块完整原文。
    """

    def __init__(
        self,
        name: str,
        description: str,
        embedding_model: EmbeddingModelBase,
        vector_store: VectorStoreBase,
        collection: str,
        metadata_filter: dict | None = None,
        rerank_model: RerankModelBase | None = None,
    ) -> None:
        """初始化父子知识库。

        Args:
            name: 知识库名称（供 Agent/前端展示）。
            description: 知识库描述（Agent 据此判断是否检索）。
            embedding_model: 嵌入模型（索引与检索必须一致）。
            vector_store: 向量库。
            collection: 物理集合名。
            metadata_filter: 多租户隔离过滤器（可选）。
            rerank_model: Rerank 精排模型（可选）。传入则启用"向量粗筛+
                rerank 精排"两阶段检索；不传则退化为纯向量检索。
        """
        self.name = name
        self.description = description
        self._rerank_model = rerank_model
        # 组合一个框架 KnowledgeBase 处理底层的嵌入/存储/向量检索
        self._kb = KnowledgeBase(
            name=name,
            description=description,
            embedding_model=embedding_model,
            vector_store=vector_store,
            collection=collection,
            metadata_filter=metadata_filter,
        )

    async def insert_document(
        self,
        chunks: list[Chunk],
        document_id: str | None = None,
        document_metadata: dict | None = None,
    ) -> str:
        """索引文档。

        直接把 ParentChildChunker 产出的【子块】灌入向量库。子块的 content
        用于生成向量，父块信息已存在于每个子块的 metadata 中。

        Args:
            chunks: ParentChildChunker.chunk() 的输出（子块列表）。
            document_id: 文档 ID（不传则自动生成）。
            document_metadata: 文档级元数据（如 filename）。

        Returns:
            str: 文档 ID。
        """
        return await self._kb.insert_document(
            chunks,
            document_id=document_id,
            document_metadata=document_metadata,
        )

    async def search_parents(
        self,
        query: str | TextBlock | DataBlock,
        top_k: int = 5,
        fetch_k: int | None = None,
        score_threshold: float | None = None,
    ) -> list[ParentHit]:
        """父子检索：召回子块 → 还原父块 → 去重 → 返回父块原文。

        Args:
            query: 查询（文本或多模态）。
            top_k: 最终返回的【父块】数量上限。
            fetch_k: 向量库先召回的【子块】数量。默认取 top_k*4，
                因为多个子块可能命中同一父块，去重后数量会减少，
                所以要多召回一些子块保证父块数量足够。
            score_threshold: 相似度阈值（可选）。

        Returns:
            list[ParentHit]: 按分数降序的父块命中列表（已按父块去重）。
        """
        # 多召回一些子块，抵消"去重后父块变少"的损耗
        fetch_k = fetch_k or top_k * 4

        # 1. 用框架 KB 做子块级向量检索（精准召回）
        child_results = await self._kb.search(
            queries=[query],
            top_k=fetch_k,
            score_threshold=score_threshold,
        )

        # 2. 按父块 ID 聚合，每个父块只保留其命中子块中的最高分
        best_by_parent: dict[str, ParentHit] = {}
        for result in child_results:
            meta = result.chunk.metadata or {}
            parent_id = meta.get(PARENT_ID_KEY)
            parent_content = meta.get(PARENT_CONTENT_KEY, "")

            # 兜底：若某些数据不是父子分块产生的（无父块信息），
            # 退化为用子块自身内容当作"父块"，保证鲁棒性
            if not parent_id:
                parent_id = f"__nochild__{result.chunk.chunk_index}"
                parent_content = (
                    result.chunk.content.text
                    if isinstance(result.chunk.content, TextBlock)
                    else parent_content
                )

            matched_child = (
                result.chunk.content.text
                if isinstance(result.chunk.content, TextBlock)
                else "[多模态内容]"
            )

            existing = best_by_parent.get(parent_id)
            if existing is None or result.score > existing.score:
                best_by_parent[parent_id] = ParentHit(
                    parent_id=parent_id,
                    content=parent_content,
                    source=result.chunk.source,
                    score=result.score,
                    matched_child=matched_child,
                )

        # 3. 按分数降序（这是"向量粗筛"的排序）
        parents = sorted(
            best_by_parent.values(),
            key=lambda h: h.score,
            reverse=True,
        )

        # 4. Rerank 精排（可选）：若配置了 rerank 模型，则对父块用
        #    [query, 父块原文] 成对精排，得到更准的相关性排序。
        #    这是"两阶段检索"的第二阶段。rerank 失败时优雅降级为向量排序。
        if self._rerank_model is not None and parents:
            parents = await self._apply_rerank(query, parents)

        # 5. 截断到 top_k 个父块
        return parents[:top_k]

    async def _apply_rerank(
        self,
        query: str | TextBlock | DataBlock,
        parents: list[ParentHit],
    ) -> list[ParentHit]:
        """用 rerank 模型对父块精排。

        Args:
            query: 查询（仅文本查询参与 rerank；多模态查询跳过）。
            parents: 向量粗筛得到的父块列表。

        Returns:
            list[ParentHit]: 精排后的父块列表（rerank 分数写回 score）。
                rerank 失败时原样返回向量排序结果（优雅降级）。
        """
        # rerank 模型只处理文本查询；非文本查询直接返回向量排序
        query_text = query if isinstance(query, str) else (
            query.text if isinstance(query, TextBlock) else None
        )
        if query_text is None:
            return parents

        try:
            documents = [p.content for p in parents]
            results = await self._rerank_model.rerank(query_text, documents)
        except Exception:  # noqa: BLE001
            # 精排失败不应导致整体检索失败——降级为向量排序结果
            return parents

        # 按 rerank 返回的顺序重排父块，并把 rerank 分数写回
        reranked: list[ParentHit] = []
        for r in results:
            hit = parents[r.index]
            hit.score = r.score  # 用更精确的 rerank 分数覆盖向量分数
            reranked.append(hit)
        return reranked
