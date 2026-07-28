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


# 全局单例，导入即用
chat_config = ChatConfig()
embedding_config = EmbeddingConfig()
rerank_config = RerankConfig()


def is_chat_ready() -> bool:
    """检查 Chat 模型配置是否已填写完整。"""
    return bool(chat_config.api_key and chat_config.base_url and chat_config.model)
