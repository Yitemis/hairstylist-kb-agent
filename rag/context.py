# -*- coding: utf-8 -*-
"""Context 工程：把检索结果拼装成结构化的模型上下文。

召回质量决定"找得到"，Context 工程决定"答得好"。本模块负责：

1. **溯源标注**：每段顶部标注来源文件 / 章节 / 分类，支持可溯源回答；
2. **类型差异化**：表格保留结构、图片附带说明与地址、文本保留原格式；
3. **有序拼装**：按相关性排序，同分时表格优先于文本优先于图片；
4. **预算控制**：按 token 预算截断，超预算时保留高分块、丢弃低分块。

产物是可直接嵌入最终 Prompt 的知识库上下文串。
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.parsers.utils import num_tokens_from_string as count_tokens
from rag.searcher import SearchHit

# 上下文默认 token 预算
DEFAULT_CONTEXT_BUDGET = 3000

# 同分排序时的类型优先级（信息密度：表格 > 文本 > 图片）
_KIND_PRIORITY = {"table": 0, "text": 1, "image": 2}


@dataclass
class ContextBlock:
    """拼装后的单条上下文（对应一个父块）。"""

    header: str
    body: str
    tokens: int


def _kind_rank(hit: SearchHit) -> int:
    """取父块主内容形态的排序优先级。"""
    ranks = [_KIND_PRIORITY.get(k, 1) for k in hit.kinds] or [1]
    return min(ranks)


def _format_header(hit: SearchHit) -> str:
    """构造溯源头：来源文件 / 章节 / 分类。"""
    parts = [hit.filename]
    if hit.section_path:
        parts.append(hit.section_path)
    if hit.category and hit.category != "general":
        parts.append(hit.category)
    return "【来源：" + " / ".join(parts) + "】"


def _format_body(hit: SearchHit) -> str:
    """按内容形态差异化格式化正文。"""
    body = hit.text.strip()
    if "image" in hit.kinds:
        body += "\n（提示：本段含图片信息，回答时可引用图片说明）"
    return body


def build_context(
    hits: list[SearchHit],
    *,
    budget: int = DEFAULT_CONTEXT_BUDGET,
) -> str:
    """把检索结果拼装成知识库上下文串。

    Args:
        hits: 检索命中的父块列表（已按相关性排序）。
        budget: 上下文 token 预算，超出后丢弃剩余低分块。

    Returns:
        结构化的知识库上下文字符串；无命中时返回空串。
    """
    blocks = assemble_blocks(hits, budget=budget)
    if not blocks:
        return ""

    sections = [f"{b.header}\n{b.body}" for b in blocks]
    return (
        "========== 知识库参考内容 ==========\n\n"
        + "\n\n".join(sections)
        + "\n\n========== 参考内容结束 =========="
    )


def assemble_blocks(
    hits: list[SearchHit],
    *,
    budget: int = DEFAULT_CONTEXT_BUDGET,
) -> list[ContextBlock]:
    """把命中排序、格式化并按预算截断为 ContextBlock 列表。"""
    # 稳定排序：先按分数降序，再按类型优先级（不改变检索主序，仅同分微调）
    ordered = sorted(
        hits,
        key=lambda h: (-h.score, _kind_rank(h)),
    )

    blocks: list[ContextBlock] = []
    used = 0
    for hit in ordered:
        header = _format_header(hit)
        body = _format_body(hit)
        tokens = count_tokens(header) + count_tokens(body)

        if used + tokens > budget and blocks:
            # 预算用尽，且已有至少一块，停止追加
            break
        blocks.append(ContextBlock(header=header, body=body, tokens=tokens))
        used += tokens

    return blocks


def build_answer_prompt(
    query: str,
    context: str,
    *,
    memory_block: str = "",
    system_role: str = "",
) -> str:
    """组装最终交给对话模型的完整 Prompt。

    Args:
        query: 用户当前问题。
        context: :func:`build_context` 产出的知识库上下文。
        memory_block: 记忆模块产出的历史/事实块（可空）。
        system_role: 角色与回答约束（可空，交由 Agent 层注入时留空）。

    Returns:
        完整 Prompt 字符串。
    """
    parts: list[str] = []
    if system_role:
        parts.append(system_role)
    if memory_block:
        parts.append(memory_block)
    if context:
        parts.append(context)
    else:
        parts.append("（知识库中未检索到相关内容，请如实告知用户并给出通用建议。）")
    parts.append(f"用户问题：{query}\n请依据以上参考内容作答，不要编造：")
    return "\n\n".join(parts)
