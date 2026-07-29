# -*- coding: utf-8 -*-
"""向量库工厂：根据配置创建 Milvus 向量库实例。

选用 Milvus 作为向量库。开发阶段可连接 Docker 部署的 Milvus 单机版，
生产阶段可连接 Milvus 集群，二者共享同一套客户端 API，切换仅需修改
``MILVUS_URI`` 配置，业务代码无需改动。

向量库通过框架的 :class:`~agentscope.rag.VectorStoreBase` 抽象接入，
上层 :class:`ParentChildKnowledgeBase` 不依赖具体实现，因此后续若需替换为
其他向量库，只需在此工厂中改动。
"""
from typing import Literal

from agentscope.rag import MilvusLiteStore, VectorStoreBase

from .config import vector_store_config


def build_vector_store() -> VectorStoreBase:
    """根据配置创建向量库实例。

    Returns:
        VectorStoreBase: 已配置好的 Milvus 向量库（尚未建立连接，
            需在 ``async with`` 上下文中使用）。
    """
    metric = vector_store_config.metric_type.upper()
    if metric not in ("COSINE", "IP", "L2"):
        metric = "COSINE"

    client_kwargs = {}
    if vector_store_config.token:
        client_kwargs["token"] = vector_store_config.token

    return MilvusLiteStore(
        uri=vector_store_config.uri,
        metric_type=metric,  # type: ignore[arg-type]
        client_kwargs=client_kwargs or None,
    )
