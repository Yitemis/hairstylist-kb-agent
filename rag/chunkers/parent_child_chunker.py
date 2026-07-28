# -*- coding: utf-8 -*-
"""父子分块器（Parent-Child Chunker）。

分块粒度存在权衡：块过小时向量检索精准但上下文残缺，块过大时上下文完整
但语义被稀释、检索召回率下降。父子分块将分块分为两层来兼顾两者：

- 父块（Parent）：较大的语义段落（默认约 512 token），保存完整原文；
- 子块（Child）：在父块内部再切成小块（默认约 128 token），用于向量检索。

检索时用子块向量做精准召回，返回子块所属父块的完整原文，从而同时获得检索
精度与上下文完整性。

实现上，框架的 :class:`Chunk` 为单层扁平结构，但带有 ``metadata`` 字段且
会被向量库持久化。因此本实现只将子块作为 :class:`Chunk` 存入向量库（子块
``content`` 用于生成向量），并把父块的完整内容与 ID 写入子块 ``metadata``。
检索命中子块后，直接从 ``metadata`` 取出父块原文，无需额外的数据库。

本类继承 :class:`~agentscope.rag.ChunkerBase`，遵守其分块契约：不跨 Section
合并；:class:`DataBlock` 整块透传不切分；``chunk_index`` 连续编号 0..N-1；
所有 Chunk 的 ``total_chunks`` 一致；每个 Chunk 的 ``source`` / ``metadata``
继承自其父 Section。
"""
from bisect import bisect_right
from itertools import accumulate

from agentscope.rag import ChunkerBase
from agentscope.rag._document import Chunk, Section
from agentscope.message import TextBlock, DataBlock

from .._utils import generate_id


# metadata 中承载父块信息的键名（集中定义，检索侧据此取父块）
PARENT_CONTENT_KEY = "parent_content"  # 父块完整原文
PARENT_ID_KEY = "parent_id"            # 父块唯一 ID
PARENT_INDEX_KEY = "parent_index"      # 父块在文档中的序号


class ParentChildChunker(ChunkerBase):
    """父子分块器。

    先把每个 Section 切成父块，再把每个父块切成子块，输出的是子块列表，
    每个子块的 metadata 里携带其父块的完整内容与 ID。
    """

    def __init__(
        self,
        parent_chunk_size: int = 512,
        child_chunk_size: int = 128,
        child_overlap: int = 24,
    ) -> None:
        """初始化父子分块器。

        Args:
            parent_chunk_size: 父块的最大近似 token 数（默认 512）。
            child_chunk_size: 子块的最大近似 token 数（默认 128）。
            child_overlap: 相邻子块之间的重叠近似 token 数（默认 24），
                防止答案正好被切在两个子块边界导致召回失败。

        Raises:
            ValueError: 参数不合法时。
        """
        if parent_chunk_size <= 0:
            raise ValueError(f"parent_chunk_size 必须为正，得到 {parent_chunk_size}")
        if child_chunk_size <= 0:
            raise ValueError(f"child_chunk_size 必须为正，得到 {child_chunk_size}")
        if child_chunk_size > parent_chunk_size:
            raise ValueError(
                f"child_chunk_size({child_chunk_size}) 不应大于 "
                f"parent_chunk_size({parent_chunk_size})",
            )
        if child_overlap < 0 or child_overlap >= child_chunk_size:
            raise ValueError(
                f"child_overlap 需满足 0 <= overlap < child_chunk_size，"
                f"得到 overlap={child_overlap}, child_chunk_size={child_chunk_size}",
            )

        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    async def chunk(self, sections: list[Section]) -> list[Chunk]:
        """把 Sections 切成子块列表，每个子块携带其父块信息。

        Args:
            sections: Parser 产出的 Section 列表（文档顺序）。

        Returns:
            list[Chunk]: 子块列表，chunk_index 连续编号，
                每个子块 metadata 含 parent_content / parent_id / parent_index。
        """
        child_chunks: list[Chunk] = []
        parent_counter = 0  # 全文档范围内的父块序号

        for section in sections:
            # --- DataBlock（图片/音视频）整块透传，不做父子切分 ---
            # 多模态内容无法按 token 切，作为一个独立子块，父块即其自身。
            if isinstance(section.content, DataBlock):
                child_chunks.append(
                    Chunk(
                        content=section.content,
                        source=section.source,
                        chunk_index=0,   # 下方统一重编号
                        total_chunks=0,  # 下方统一重编号
                        metadata={
                            **dict(section.metadata),
                            PARENT_ID_KEY: generate_id(),
                            PARENT_INDEX_KEY: parent_counter,
                            # 多模态无文本父内容，留空字符串
                            PARENT_CONTENT_KEY: "",
                        },
                    ),
                )
                parent_counter += 1
                continue

            # --- 文本 Section：先切父块，再在父块内切子块 ---
            text = section.content.text
            parent_texts = self._split_text(
                text,
                self.parent_chunk_size,
                overlap=0,  # 父块之间不重叠，保证父块原文互不冗余
            )

            for parent_text in parent_texts:
                parent_id = generate_id()
                parent_index = parent_counter
                parent_counter += 1

                # 在当前父块内切子块（子块之间带 overlap）
                child_texts = self._split_text(
                    parent_text,
                    self.child_chunk_size,
                    overlap=self.child_overlap,
                )

                for child_text in child_texts:
                    child_chunks.append(
                        Chunk(
                            # 子块 content 用于生成向量（精准检索）
                            content=TextBlock(text=child_text),
                            source=section.source,
                            chunk_index=0,   # 下方统一重编号
                            total_chunks=0,  # 下方统一重编号
                            metadata={
                                # 继承 Section 的元数据（如页码）
                                **dict(section.metadata),
                                # 父块信息：检索命中子块后据此取回父块原文
                                PARENT_ID_KEY: parent_id,
                                PARENT_INDEX_KEY: parent_index,
                                PARENT_CONTENT_KEY: parent_text,
                            },
                        ),
                    )

        # --- 统一重编号，满足框架契约：chunk_index 连续、total_chunks 一致 ---
        total = len(child_chunks)
        for index, chunk in enumerate(child_chunks):
            chunk.chunk_index = index
            chunk.total_chunks = total

        return child_chunks

    # ------------------------------------------------------------------
    # 文本切分核心算法（按近似 token = utf-8 字节数 // 4）
    # ------------------------------------------------------------------

    def _split_text(
        self,
        text: str,
        size: int,
        overlap: int,
    ) -> list[str]:
        """把文本切成每片至多 size 个近似 token 的片段。

        近似 token 数 = utf-8 字节数 // 4，与框架 count_tokens 的估算一致，
        避免依赖具体分词器。相邻片段共享约 overlap 个 token。

        Args:
            text: 待切分文本。
            size: 每片最大近似 token 数。
            overlap: 相邻片段重叠的近似 token 数。

        Returns:
            list[str]: 文本片段（文档顺序）。
        """
        if self._approx_tokens(text) <= size:
            return [text] if text else []

        # 每个字符结束后的累计 utf-8 字节数，使得
        # text[i:j] 的字节长度 == byte_offsets[j] - byte_offsets[i]
        byte_offsets = [0, *accumulate(len(c.encode("utf-8")) for c in text)]

        size_bytes = size * 4
        overlap_bytes = overlap * 4

        pieces: list[str] = []
        start = 0
        while start < len(text):
            # 在字节预算内能取到的最大结束位置
            end = bisect_right(byte_offsets, byte_offsets[start] + size_bytes) - 1
            # 保证至少前进一个字符（应对单字符 utf-8 编码超预算的极端情况）
            end = max(end, start + 1)
            pieces.append(text[start:end])

            if end >= len(text):
                break

            # 回退 overlap 字节作为下一片的起点，同时保证前进
            next_start = (
                bisect_right(byte_offsets, byte_offsets[end] - overlap_bytes) - 1
            )
            start = max(next_start, start + 1)

        return pieces

    @staticmethod
    def _approx_tokens(text: str) -> int:
        """近似 token 数 = utf-8 字节数 // 4。"""
        return len(text.encode("utf-8")) // 4
