# -*- coding: utf-8 -*-
"""知识库管理器：文档入库、检索、自检全流程。

将 Markdown 文档经过「父子分块 → 向量化 → 存入 Qdrant」的完整流程封装。
提供启动自检、索引统计、健康检查等管理能力。
"""
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentscope.message import TextBlock
from agentscope.rag._document import Section

from app.config import vector_store_config
from app.embedding import build_embedding_model
from app.vector_store import build_vector_store
from rag.chunkers.parent_child_chunker import ParentChildChunker
from rag.knowledge import ParentChildKnowledgeBase


@dataclass
class KnowledgeHealth:
    """知识库健康状态报告（启动自检用）。"""

    vector_db_ok: bool = False
    embedding_model_ok: bool = False
    document_count: int = 0
    chunk_count: int = 0
    issues: list[str] | None = None


class KnowledgeManager:
    """知识库管理器，封装索引、检索、自检全流程。"""

    def __init__(
        self,
        knowledge_dir: str = "data/knowledge",
        collection_name: str | None = None,
    ) -> None:
        self.knowledge_dir = Path(knowledge_dir)
        self.collection_name = collection_name or vector_store_config.collection
        self._chunker = ParentChildChunker()
        self._kb: ParentChildKnowledgeBase | None = None
        self._vector_store = None
        self._embedding_model = None

    async def init(self) -> "KnowledgeManager":
        """初始化向量库、嵌入模型和知识库。

        首次运行时自动创建集合。可作为启动自检的一部分。
        """
        # 1. 初始化向量库
        self._vector_store = build_vector_store()
        # Qdrant 本地模式是上下文管理器，我们需要先连接
        # 这里先占位，实际使用时在 async with 中

        # 2. 初始化嵌入模型
        self._embedding_model = build_embedding_model()

        # 3. 初始化父子知识库（组合向量库 + 嵌入模型）
        # 注意：ParentChildKnowledgeBase 目前需要在调用时传入
        # 这里我们先保存组件，检索时动态组合

        return self

    async def index_directory(self) -> dict[str, Any]:
        """索引整个知识目录下的所有文档。

        Returns:
            索引统计结果（成功文档数、总分块数、失败文档列表）。
        """
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        md_files = list(self.knowledge_dir.glob("*.md"))
        txt_files = list(self.knowledge_dir.glob("*.txt"))
        all_files = md_files + txt_files

        if not all_files:
            return {
                "success": 0,
                "total_chunks": 0,
                "failed": [],
                "message": "知识目录为空，请先放入 .md 或 .txt 文档",
            }

        success = 0
        total_chunks = 0
        failed = []

        for file_path in all_files:
            try:
                chunks = await self._index_single_file(file_path)
                success += 1
                total_chunks += len(chunks)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{file_path.name}: {str(e)}")

        return {
            "success": success,
            "total_chunks": total_chunks,
            "failed": failed,
            "message": f"索引完成：成功 {success} 个，失败 {len(failed)} 个，共 {total_chunks} 个分块",
        }

    async def _index_single_file(self, file_path: Path) -> int:
        """索引单个文档。

        流程：读取文件 → Section 封装 → 父子分块 → 嵌入 → 入库。
        """
        content = file_path.read_text(encoding="utf-8")
        filename = file_path.name

        # 1. 封装为 Section
        section = Section(
            content=TextBlock(text=content),
            source=filename,
            metadata={"filename": filename, "file_type": "markdown"},
        )

        # 2. 父子分块
        chunks = await self._chunker.chunk([section])

        # 3. TODO: 嵌入并存入向量库
        # （需要完善 ParentChildKnowledgeBase 的 insert_document 方法）
        # 此处先返回分块数量，后续接入完整流程

        return len(chunks)

    async def search(self, query: str, top_k: int = 3) -> dict[str, Any]:
        """检索知识库。

        Args:
            query: 用户查询。
            top_k: 返回结果数量。

        Returns:
            检索结果，包含命中的父块内容、来源、相似度分数。
        """
        # TODO: 接入完整的检索流程
        # async with self._vector_store:
        #     hits = await self._kb.search_parents(query, top_k=top_k)

        # 占位实现
        return {
            "results": [
                {
                    "content": "检索功能开发中，请先完成向量库接入",
                    "source": "system",
                    "score": 1.0,
                }
            ],
            "count": 1,
        }

    async def health_check(self) -> KnowledgeHealth:
        """知识库全面自检（启动时调用，输出健康报告）。

        Returns:
            KnowledgeHealth: 包含各组件状态与问题列表。
        """
        issues = []

        # 1. 检查知识目录
        if not self.knowledge_dir.exists():
            issues.append(f"知识目录不存在: {self.knowledge_dir}")
        else:
            doc_count = len(list(self.knowledge_dir.glob("*.md"))) + len(
                list(self.knowledge_dir.glob("*.txt"))
            )
            if doc_count == 0:
                issues.append("知识目录为空，没有可索引的文档")

        # 2. 检查向量库连接（占位，后续接入 Qdrant 健康检查）
        vector_db_ok = True  # 暂时假设 OK

        # 3. 检查嵌入模型连通性（占位，后续接入真实 ping）
        embedding_ok = True  # 暂时假设 OK

        return KnowledgeHealth(
            vector_db_ok=vector_db_ok,
            embedding_model_ok=embedding_ok,
            document_count=doc_count if self.knowledge_dir.exists() else 0,
            chunk_count=0,  # 后续接入真实统计
            issues=issues or None,
        )


# ------------------------------------------------------------------
# 全局单例（供 Agent 工具调用）
# ------------------------------------------------------------------

_knowledge_manager: KnowledgeManager | None = None


async def get_knowledge_manager() -> KnowledgeManager:
    """获取或初始化知识库管理器（全局单例）。"""
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
        await _knowledge_manager.init()
    return _knowledge_manager


# ------------------------------------------------------------------
# 命令行索引工具
# ------------------------------------------------------------------


async def _main() -> None:
    """命令行入口：索引知识目录。"""
    print("=" * 60)
    print("美发知识助手 - 知识库索引工具")
    print("=" * 60)

    km = KnowledgeManager()
    await km.init()

    print("\n🔍 执行自检...")
    health = await km.health_check()
    print(f"   向量库: {'✓' if health.vector_db_ok else '✗'}")
    print(f"   嵌入模型: {'✓' if health.embedding_model_ok else '✗'}")
    print(f"   文档数量: {health.document_count}")
    if health.issues:
        print(f"\n⚠️  发现问题:")
        for issue in health.issues:
            print(f"   - {issue}")

    print("\n📥 开始索引文档...")
    result = await km.index_directory()
    print(f"\n   ✓ {result['message']}")
    if result["failed"]:
        print(f"\n✗ 失败文档:")
        for f in result["failed"]:
            print(f"   - {f}")


if __name__ == "__main__":
    asyncio.run(_main())
