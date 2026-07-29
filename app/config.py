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
    """向量库配置（Qdrant）。

    Qdrant 支持多种运行方式，本项目优先使用纯 Python 的本地模式：

    - ``local``：Python 内嵌的本地持久化模式，数据存指定路径的
      SQLite 格式文件，零部署、零 Docker，仅需安装 ``qdrant-client``，
      适合开发与快速验证；
    - ``memory``：纯内存模式，重启即失，适合单元测试；
    - ``remote``：连接独立的 Qdrant 服务，生产环境使用。

    不同模式通过同一个 ``QdrantStore`` API 接入，切换时业务代码不变。
    """

    mode: str = os.getenv("QDRANT_MODE", "local")
    path: str = os.getenv("QDRANT_PATH", "data/qdrant")
    url: str = os.getenv("QDRANT_URL", "")
    api_key: str = os.getenv("QDRANT_API_KEY", "")
    collection: str = os.getenv("VECTOR_COLLECTION", "hairstylist_kb")
    metric_type: str = os.getenv("QDRANT_METRIC_TYPE", "COSINE")


# 全局单例，导入即用
chat_config = ChatConfig()
embedding_config = EmbeddingConfig()
rerank_config = RerankConfig()
vector_store_config = VectorStoreConfig()


def is_chat_ready() -> bool:
    """检查 Chat 模型配置是否已填写完整。"""
    return bool(chat_config.api_key and chat_config.base_url and chat_config.model)
