# -*- coding: utf-8 -*-
"""Rerank 重排序模型的抽象基类。

Rerank 是两阶段检索的第二阶段。向量检索将查询和文档各自编码为向量后比较
相似度，速度快但会损失细节；Rerank 将查询与每个候选文档成对输入交叉编码
（cross-encoder）模型，直接输出相关性分数，精度更高。

两阶段检索流程为：向量检索召回 Top-N 候选，Rerank 对候选精排后取 Top-K，
再交给下游使用。

不同厂商的 Rerank API 格式各异，此处定义统一抽象接口，上层仅依赖该接口，
具体厂商实现可自由替换。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RerankResult:
    """单条重排结果。"""

    index: int
    """该文档在输入候选列表中的原始下标（用于映射回原始对象）。"""
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
