# -*- coding: utf-8 -*-
"""RerankModelBase —— Rerank 重排序模型的抽象基类。

【为什么需要 Rerank（重排序）】
向量检索（召回）是"粗筛"：它把查询和文档都压成一个向量，用余弦相似度找相近的。
这种方式快，但有局限——向量是对整段文本的"平均语义压缩"，会丢失细节，常出现
"看起来相关但答非所问"的结果。

Rerank（精排）是"精筛"：它把 [查询, 每个候选文档] 成对地喂给一个专门的
交叉编码（cross-encoder）模型，让模型直接判断"这个文档对这个查询到底有多相关"，
输出一个精确的相关性分数。因为查询和文档是一起进模型的（而非各自压成向量再比），
所以能捕捉细粒度的语义匹配，准确率显著高于纯向量检索。

【两阶段检索（本项目的核心技术亮点之一）】
  向量检索召回 Top-N（如 20 个，快速粗筛）
      ↓
  Rerank 精排，取 Top-K（如 3 个，精准）
      ↓
  喂给 LLM
这是工业界 RAG 提升质量最立竿见影的手段。框架 AgentScope 本身没有 rerank 能力，
本模块从零实现，是本项目区别于"裸用框架"的差异化能力。

【设计为抽象基类】
不同厂商的 rerank API 格式不同（火山、通义、开源 bge 等）。定义一个统一抽象，
上层知识库只依赖这个接口，具体厂商可自由替换——与框架"模型可插拔"的理念一致。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RerankResult:
    """单条重排结果。"""

    index: int
    """该文档在【输入候选列表】中的原始下标（用于映射回原始对象）。"""
    score: float
    """rerank 模型给出的相关性分数（越高越相关）。"""


class RerankModelBase(ABC):
    """Rerank 重排序模型抽象基类。

    子类只需实现 rerank(query, documents) -> list[RerankResult]。
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """对候选文档按与 query 的相关性重新排序。

        Args:
            query: 查询文本。
            documents: 候选文档文本列表（来自向量检索的粗筛结果）。
            top_n: 只返回排名前 top_n 个；None 表示返回全部（已排序）。

        Returns:
            list[RerankResult]: 按相关性分数降序排列，每项含原始下标和分数。
        """
