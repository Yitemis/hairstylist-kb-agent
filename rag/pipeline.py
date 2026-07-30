# -*- coding: utf-8 -*-
"""RAG 索引与检索管道（父子分块 + 混合检索）。

把「解析 → 父子分块 → 元数据标注 → 生成索引记录」和「多路召回 → 融合 →
父块聚合 → 加权重排」两条主链路收敛到一处。本层不直接依赖向量库或大模型
服务，只处理数据结构与排序逻辑，因此可离线测试；向量通道与嵌入由 RAG 引擎
在外层注入。

父子分块（Parent-Child）核心：

* 索引侧：以**子块（Segment）**为最小单元建记录，每条记录携带其**父块
  （Block）的完整文本**。子块小而精准，用于向量化与 BM25 命中。
* 检索侧：命中子块后**按父块聚合去重**，返回父块完整文本作为上下文——
  兼顾"检索精度（子块）"与"上下文完整（父块）"。

核心数据结构：

* :class:`IndexRecord` —— 子块级检索单元（可入向量库 / BM25）。
* :class:`ParentHit`   —— 检索结果，父块级上下文 + 命中子块信息。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.parsers import parse_document
from rag.parsers.doc_types import Block, Segment, SegmentKind
from rag.retrieval import (
    KeywordIndex,
    apply_boosts,
    extract_models,
    reciprocal_rank_fusion,
)


@dataclass
class IndexRecord:
    """子块级检索单元（父子分块中的"子"）。

    Attributes:
        record_id: 子块全局唯一 ID（``tenant:doc:父序号:子序号``）。
        text: 子块可检索文本（向量化与 BM25 的对象，小而精准）。
        parent_id: 所属父块 ID（``tenant:doc:父序号``），聚合去重用。
        parent_text: 父块完整文本，命中后作为上下文返回。
        tenant_id: 租户 ID，多租户硬隔离维度。
        permission: 权限标签（如 public / A / B），角色隔离维度。
        doc_id: 所属文档 ID。
        filename: 来源文件名，用于溯源。
        category: 业务分类。
        section: 章节路径面包屑。
        kind: 子块内容形态（text/table/image 之一）。
        models: 子块文本中出现的型号 / 编码 token。
        metadata: 其余自由元数据。
    """

    record_id: str
    text: str
    parent_id: str
    parent_text: str
    tenant_id: str = "default"
    permission: str = "public"
    doc_id: str = ""
    filename: str = ""
    category: str = "general"
    section: list[str] = field(default_factory=list)
    kind: str = SegmentKind.TEXT.value
    models: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """转为向量库 payload（扁平化，便于过滤与命中后回溯父块）。"""
        return {
            "record_id": self.record_id,
            "text": self.text,
            "parent_id": self.parent_id,
            "parent_text": self.parent_text,
            "tenant_id": self.tenant_id,
            "permission": self.permission,
            "doc_id": self.doc_id,
            "filename": self.filename,
            "category": self.category,
            "section": self.section,
            "section_path": " / ".join(self.section),
            "kind": self.kind,
            "models": self.models,
            **self.metadata,
        }


@dataclass
class ParentHit:
    """检索结果：父块级上下文 + 命中子块信息。

    Attributes:
        parent_id: 父块 ID。
        parent_text: 父块完整文本（提供给模型的上下文）。
        matched_text: 实际命中的子块文本（可用于高亮 / 调试）。
        score: 最终得分（融合 + 加权后）。
        filename: 来源文件名。
        section: 章节路径。
        kinds: 该父块被召回子块所含的内容形态集合。
        record: 命中的子块记录（保留完整元数据）。
    """

    parent_id: str
    parent_text: str
    matched_text: str
    score: float
    filename: str
    section: list[str]
    kinds: set[str]
    record: IndexRecord


# ------------------------------------------------------------------
# 索引侧：文档 -> 父块 -> 子块级 IndexRecord 列表
# ------------------------------------------------------------------


def build_records(
    file_uri: str,
    *,
    doc_id: str,
    filename: str | None = None,
    tenant_id: str = "default",
    permission: str = "public",
    category: str = "general",
) -> list[IndexRecord]:
    """解析文档并生成子块级索引记录（父子分块）。

    先把文档解析为父块（Block）列表，再把每个父块内的子块（Segment）各生成
    一条记录，记录携带父块完整文本，实现"子块检索、父块上下文"。

    Args:
        file_uri: 文件路径或安全 URL。
        doc_id: 文档唯一 ID。
        filename: 来源文件名，缺省从 file_uri 推断。
        tenant_id: 租户 ID。
        permission: 权限标签。
        category: 业务分类。

    Returns:
        子块级 IndexRecord 列表。
    """
    blocks = parse_document(file_uri, filename)
    name = filename or file_uri.replace("\\", "/").split("/")[-1]

    records: list[IndexRecord] = []
    for parent_idx, block in enumerate(blocks):
        parent_id = f"{tenant_id}:{doc_id}:{parent_idx}"
        for child_idx, segment in enumerate(block.segments):
            records.append(
                _segment_to_record(
                    segment, block, parent_id=parent_id, child_idx=child_idx,
                    doc_id=doc_id, filename=name, tenant_id=tenant_id,
                    permission=permission, category=category,
                ),
            )
    return records


def _segment_to_record(
    segment: Segment,
    parent: Block,
    *,
    parent_id: str,
    child_idx: int,
    doc_id: str,
    filename: str,
    tenant_id: str,
    permission: str,
    category: str,
) -> IndexRecord:
    """把单个子块（Segment）转成子块级 IndexRecord。"""
    # 子块章节优先用自身的，缺省回退到父块章节
    section = list(segment.section) if segment.section else list(parent.section)
    return IndexRecord(
        record_id=f"{parent_id}:{child_idx}",
        text=segment.text,
        parent_id=parent_id,
        parent_text=parent.text,
        tenant_id=tenant_id,
        permission=permission,
        doc_id=doc_id,
        filename=filename,
        category=category,
        section=section,
        kind=segment.kind.value,
        models=sorted(set(extract_models(segment.text))),
        metadata=dict(parent.metadata),
    )


# ------------------------------------------------------------------
# 检索侧：权限过滤 + 混合检索 + 父块聚合
# ------------------------------------------------------------------


def visible(record: IndexRecord, tenant_id: str, roles: set[str] | None) -> bool:
    """判断记录对当前租户 / 角色是否可见（硬隔离）。

    规则：租户必须匹配；权限为 public 对所有角色可见，否则要求角色集合包含
    该权限标签。``roles`` 为空表示仅能看 public。
    """
    if record.tenant_id != tenant_id:
        return False
    if record.permission == "public":
        return True
    return bool(roles) and record.permission in roles


def hybrid_rank(
    query: str,
    records: list[IndexRecord],
    vector_ranking: list[str],
    *,
    tenant_id: str = "default",
    roles: set[str] | None = None,
    rrf_k: int = 60,
    vector_weight: float = 1.0,
    keyword_weight: float = 1.0,
    top_k: int = 5,
) -> list[ParentHit]:
    """父子分块两阶段混合检索。

    流程：
    1. 权限 + 租户硬过滤（子块级）；
    2. BM25 关键词通道在可见子块上召回；
    3. 与向量通道的子块排名做 RRF 融合；
    4. **按父块聚合**：同一父块取其命中子块的最高融合分，实现父子回溯；
    5. 融合分归一化后做型号 / 类型加权；
    6. 返回父块级 :class:`ParentHit`（父块全文作上下文）。

    向量通道的子块排序由外层（引擎）传入 ``vector_ranking``（record_id 列表，
    越靠前越相关），本函数负责其余全部逻辑，便于离线测试与复用。

    Args:
        query: 用户查询。
        records: 候选子块记录全集（同一知识库范围）。
        vector_ranking: 向量检索给出的子块 record_id 排名。
        tenant_id: 当前租户。
        roles: 当前用户角色集合，用于权限过滤。
        rrf_k: RRF 平滑常数。
        vector_weight: 向量通道融合权重。
        keyword_weight: 关键词通道融合权重。
        top_k: 返回父块条数。

    Returns:
        ParentHit 列表，按最终得分降序。
    """
    # 1) 子块级权限 + 租户硬过滤
    allowed = {
        r.record_id: r for r in records if visible(r, tenant_id, roles)
    }
    if not allowed:
        return []

    # 2) BM25 关键词通道（仅在可见子块内建索引）
    kw = KeywordIndex()
    for rid, rec in allowed.items():
        kw.add(rid, rec.text)
    kw.build()
    keyword_ranking = [rid for rid, _ in kw.search(query, top_k=len(allowed))]

    # 3) 向量子块排名落在可见集合内
    vector_ranking = [rid for rid in vector_ranking if rid in allowed]

    # 4) RRF 融合两路子块排名
    fused = reciprocal_rank_fusion(
        [vector_ranking, keyword_ranking],
        weights=[vector_weight, keyword_weight],
        k=rrf_k,
    )
    if not fused:
        return []

    # 5) 按父块聚合：每个父块保留命中子块的最高分，并记录该命中子块
    parent_best: dict[str, tuple[float, IndexRecord]] = {}
    parent_kinds: dict[str, set[str]] = {}
    for rid, score in fused:
        rec = allowed[rid]
        parent_kinds.setdefault(rec.parent_id, set()).add(rec.kind)
        if rec.parent_id not in parent_best or score > parent_best[rec.parent_id][0]:
            parent_best[rec.parent_id] = (score, rec)

    # 6) 父块融合分归一化到 [0,1]，再做型号 / 类型加权
    ordered = sorted(parent_best.items(), key=lambda kv: kv[1][0], reverse=True)
    max_score = ordered[0][1][0] or 1.0
    normalized = [(pid, sc / max_score) for pid, (sc, _rec) in ordered]
    kinds_of = {pid: parent_kinds[pid] for pid, _ in normalized}
    text_of = {pid: parent_best[pid][1].parent_text for pid, _ in normalized}
    boosted = apply_boosts(query, normalized, kinds_of, text_of)

    # 7) 组装父块级结果
    hits: list[ParentHit] = []
    for pid, score in boosted[:top_k]:
        _sc, rec = parent_best[pid]
        hits.append(
            ParentHit(
                parent_id=pid,
                parent_text=rec.parent_text,
                matched_text=rec.text,
                score=score,
                filename=rec.filename,
                section=list(rec.section),
                kinds=parent_kinds[pid],
                record=rec,
            ),
        )
    return hits


def section_recall(
    records: list[IndexRecord],
    section_query: str,
    *,
    tenant_id: str = "default",
    roles: set[str] | None = None,
) -> list[ParentHit]:
    """章节定向召回：返回章节匹配的全部父块（去重、保持顺序）。

    当用户问"某章节讲了什么"时，向量检索可能只召回部分子块。此函数按章节
    面包屑或子块标题做匹配，强制召回命中章节下的**所有父块**（按父块去重），
    保证内容完整。

    Args:
        records: 候选子块记录全集。
        section_query: 章节名或关键词（在面包屑任意层级或标题行中包含即命中）。
        tenant_id: 当前租户。
        roles: 当前用户角色集合。

    Returns:
        命中章节的父块 ParentHit 列表（保持文档顺序，父块去重）。
    """
    key = section_query.strip()
    seen: set[str] = set()
    hits: list[ParentHit] = []
    for rec in records:
        if not visible(rec, tenant_id, roles):
            continue
        if rec.parent_id in seen:
            continue
        in_crumb = any(key in crumb for crumb in rec.section)
        in_heading = any(
            key in line.lstrip("# ").strip()
            for line in rec.parent_text.splitlines()
            if line.lstrip().startswith("#")
        )
        if in_crumb or in_heading:
            seen.add(rec.parent_id)
            hits.append(
                ParentHit(
                    parent_id=rec.parent_id,
                    parent_text=rec.parent_text,
                    matched_text=rec.text,
                    score=1.0,
                    filename=rec.filename,
                    section=list(rec.section),
                    kinds={rec.kind},
                    record=rec,
                ),
            )
    return hits
