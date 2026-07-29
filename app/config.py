# -*- coding: utf-8 -*-
"""配置管理模块。

统一从 ``.env`` 文件读取模型、向量库等配置。集中管理配置以支持模型可插拔：
切换模型厂商或型号时只需修改 ``.env``，无需改动代码。
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件
_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".env",
)
load_dotenv(_ENV_PATH, override=True)


@dataclass
class ChatConfig:
    """Chat 对话模型配置。"""

    api_key: str = os.getenv("CHAT_API_KEY", "")
    base_url: str = os.getenv("CHAT_BASE_URL", "")
    model: str = os.getenv("CHAT_MODEL", "")


@dataclass
class EmbeddingConfig:
    """Embedding 嵌入模型配置。"""

    api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    base_url: str = os.getenv("EMBEDDING_BASE_URL", "")
    model: str = os.getenv("EMBEDDING_MODEL", "")
    dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))


@dataclass
class RerankConfig:
    """Rerank 重排模型配置。"""

    api_key: str = os.getenv("RERANK_API_KEY", "")
    base_url: str = os.getenv("RERANK_BASE_URL", "")
    model: str = os.getenv("RERANK_MODEL", "")


@dataclass
class VectorStoreConfig:
    """向量库配置（Milvus）。

    通过 ``uri`` 决定运行形态，两者共享同一套 ``MilvusClient`` API：

    - 本地文件（如 ``./data/milvus.db``）：Milvus Lite 嵌入式实例，
      零部署，仅需安装 pymilvus，适合快速验证（注：不支持 Windows）；
    - 远程服务（如 ``http://localhost:19530``）：连接独立部署的 Milvus
      单机版或集群，生产环境使用。

    因两种形态 API 一致，从开发切换到生产只需修改 ``uri``，业务代码无需改动。
    """

    uri: str = os.getenv("MILVUS_URI", "http://localhost:19530")
    token: str = os.getenv("MILVUS_TOKEN", "")
    collection: str = os.getenv("VECTOR_COLLECTION", "hairstylist_kb")
    metric_type: str = os.getenv("MILVUS_METRIC_TYPE", "COSINE")


# 全局单例，导入即用
chat_config = ChatConfig()
embedding_config = EmbeddingConfig()
rerank_config = RerankConfig()
vector_store_config = VectorStoreConfig()


def is_chat_ready() -> bool:
    """检查 Chat 模型配置是否已填写完整。"""
    return bool(chat_config.api_key and chat_config.base_url and chat_config.model)
