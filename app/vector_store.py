# -*- coding: utf-8 -*-
"""向量库工厂：根据配置创建 Qdrant 向量库实例。

选用 Qdrant 作为向量库。优先使用本地模式（纯 Python 嵌入式，零 Docker，
数据持久化到本地文件），适合开发与快速验证；生产环境可切换至远程 Qdrant
服务或集群。两种模式共享同一套客户端 API，切换时业务代码无需改动。

向量库通过框架的 :class:`~agentscope.rag.VectorStoreBase` 抽象接入，
上层 :class:`ParentChildKnowledgeBase` 不依赖具体实现，因此后续若需替换为
其他向量库，只需在此工厂中改动。
"""
import os

from agentscope.rag import QdrantStore, VectorStoreBase

from .config import vector_store_config


def build_vector_store() -> VectorStoreBase:
    """根据配置创建向量库实例。

    Returns:
        VectorStoreBase: 已配置好的 Qdrant 向量库（尚未建立连接，
            需在 ``async with`` 上下文中使用）。
    """
    mode = vector_store_config.mode.lower()

    if mode == "local":
        # 本地持久化模式：数据存 SQLite 文件，零 Docker
        path = vector_store_config.path
        os.makedirs(os.path.dirname(path) if "/" in path else ".", exist_ok=True)
        return QdrantStore(location=path)

    elif mode == "memory":
        # 纯内存模式：数据不持久化，适合单元测试
        return QdrantStore(location=":memory:")

    elif mode == "remote":
        # 远程服务模式：连接独立部署的 Qdrant
        client_kwargs = {}
        if vector_store_config.api_key:
            client_kwargs["api_key"] = vector_store_config.api_key
        return QdrantStore(url=vector_store_config.url, **client_kwargs)

    else:
        raise ValueError(
            f"未知向量库模式: {mode}，支持 'local'/'memory'/'remote'",
        )
