# -*- coding: utf-8 -*-
"""查询改写 6 策略（借鉴 ekbs 召回优化）。

为什么需要？
- 用户 query 经常口语化、模糊、不完整
  - "洗发用啥水温" → 检索失败（文档说"洗发的水温控制标准"）
  - "染发前要做什么" → 召回文档不包含"什么"（是文档章节标题的问题）
- 单一 embedding 难以应对所有 query 类型
- **多策略并行 + RRF 融合** = 召回率提升 30-50%

6 策略：
1. rewrite        LLM 改写（口语化→专业）
2. subquery       复杂问题拆解成多个子问题
3. hyde           假设文档嵌入（先猜答案再嵌）
4. stepback       后退一步（先问抽象再问具体）
5. multiquery     多角度（生成 N 个等价 query）
6. selfquery      提取 metadata filter（按 category 分流）
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RewrittenQuery:
    """改写后的查询。"""
    original: str
    strategy: str  # rewrite/subquery/hyde/stepback/multiquery/selfquery
    candidates: List[str]  # 候选 queries（可能多个）
    filters: dict = field(default_factory=dict)  # metadata filters (selfquery 用)


# 复用 LLM 调用工具
async def _llm_call(prompt: str, system: str = "你是查询优化专家。") -> str:
    """调 LLM 改写。"""
    from app.core.model_factory import get_model
    from agentscope.message import TextBlock, UserMsg
    model = get_model("chat")
    sys_msg = UserMsg(name="system", content=[TextBlock(text=system)])
    user_msg = UserMsg(name="user", content=[TextBlock(text=prompt)])
    resp = await model([sys_msg, user_msg], stream=False)
    # 提取文本
    if hasattr(resp, "content") and resp.content:
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text:
                text += block.text
        return text.strip()
    return ""


# ===================================================================
# 6 个策略
# ===================================================================

async def rewrite(original: str) -> RewrittenQuery:
    """策略 1: LLM 改写（口语化→专业）。"""
    prompt = f"""改写用户查询为专业美发术语（保留原意，不要回答问题）。

用户查询: {original}
专业改写: """
    rewritten = await _llm_call(prompt)
    if not rewritten or len(rewritten) < 2:
        return RewrittenQuery(original=original, strategy="rewrite", candidates=[original])
    return RewrittenQuery(original=original, strategy="rewrite", candidates=[rewritten])


async def subquery(original: str) -> RewrittenQuery:
    """策略 2: 复杂问题拆解成多个子问题（JSON 数组返回）。"""
    prompt = f"""把复杂问题拆成 2-4 个简单子问题（JSON 数组输出）。

复杂问题: {original}
子问题（JSON 数组）: """
    text = await _llm_call(prompt)
    # 解析 JSON
    candidates = [original]
    try:
        m = re.search(r'\[(.+?)\]', text, re.DOTALL)
        if m:
            arr = json.loads(m.group(0))
            if isinstance(arr, list) and arr:
                candidates = [str(s) for s in arr if s]
    except (json.JSONDecodeError, ValueError):
        # 兜底：按行拆
        lines = [l.strip("- 。，").strip() for l in text.split("\n") if l.strip()]
        if lines:
            candidates = lines[:4]
    return RewrittenQuery(original=original, strategy="subquery", candidates=candidates)


async def hyde(original: str) -> RewrittenQuery:
    """策略 3: HyDE（Hypothetical Document Embeddings）。

    假设一篇文档回答了这个问题，把假设文档作为 query（不准确但语义接近）。
    """
    prompt = f"""写一段 100-200 字的假设性美发知识文档来回答这个问题（不需要真实）。

问题: {original}
假设文档: """
    hypo = await _llm_call(prompt)
    if not hypo:
        return RewrittenQuery(original=original, strategy="hyde", candidates=[original])
    return RewrittenQuery(original=original, strategy="hyde", candidates=[hypo])


async def stepback(original: str) -> RewrittenQuery:
    """策略 4: Step-Back Prompting（先回答抽象再具体）。"""
    prompt = f"""把具体问题抽象为更高层次的问题（知识/原理层面）。

具体问题: {original}
抽象问题: """
    abstract = await _llm_call(prompt)
    if not abstract:
        return RewrittenQuery(original=original, strategy="stepback", candidates=[original])
    return RewrittenQuery(original=original, strategy="stepback", candidates=[abstract])


async def multiquery(original: str, n: int = 3) -> RewrittenQuery:
    """策略 5: 多角度（生成 N 个等价 query）。"""
    prompt = f"""从 {n} 个不同角度重写这个问题（保留核心意图，JSON 数组）。

问题: {original}
{n}个角度: """
    text = await _llm_call(prompt)
    candidates = [original]
    try:
        m = re.search(r'\[(.+?)\]', text, re.DOTALL)
        if m:
            arr = json.loads(m.group(0))
            if isinstance(arr, list) and arr:
                candidates = [str(s) for s in arr if s][:n]
    except (json.JSONDecodeError, ValueError):
        lines = [l.strip("- 。，12345.").strip() for l in text.split("\n") if l.strip()]
        if lines:
            candidates = lines[:n]
    return RewrittenQuery(original=original, strategy="multiquery", candidates=candidates)


# 类别字典（可由外部配置注入）
CATEGORY_KEYWORDS = {
    "haircare": ["洗发", "护发", "头发", "头皮", "发膜", "护理"],
    "coloring": ["染发", "染色", "漂发", "上色", "颜色", "色号"],
    "styling": ["造型", "剪发", "理发", "刘海", "卷发", "烫发"],
    "skincare": ["护肤", "洁面", "面膜", "面霜", "精华", "防晒"],
    "nail": ["美甲", "指甲", "甲油", "光疗", "款式"],
    "consultation": ["咨询", "建议", "推荐", "什么好", "怎么选"],
}


async def selfquery(original: str) -> RewrittenQuery:
    """策略 6: 提取 metadata filter（按 category 分流）。

    关键：
    - 一次性扫完所有 categories（不动 query_main）
    - 主体清理只剔除**业务强相关**的关键词（避免"推荐"等泛词被误删）
    - consultation 类只做检测，不做主体清理
    """
    detected_categories: list[str] = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in original:
                detected_categories.append(cat)
                break

    # 只清理业务强相关的 category 关键词（haircare/coloring/styling/skincare/nail）
    # consultation 类的"推荐/什么好"是泛词，不应删
    BUSINESS_CATEGORIES = {"haircare", "coloring", "styling", "skincare", "nail"}
    query_main = original
    for cat in detected_categories:
        if cat in BUSINESS_CATEGORIES:
            for kw in CATEGORY_KEYWORDS[cat]:
                query_main = query_main.replace(kw, "")
    query_main = query_main.strip(" ，。?？") or original

    return RewrittenQuery(
        original=original,
        strategy="selfquery",
        candidates=[query_main],
        filters={"category": detected_categories} if detected_categories else {},
    )


# ===================================================================
# 策略注册表 + 并行执行
# ===================================================================

STRATEGIES: dict[str, Callable] = {
    "rewrite": rewrite,
    "subquery": subquery,
    "hyde": hyde,
    "stepback": stepback,
    "multiquery": multiquery,
    "selfquery": selfquery,
}


async def rewrite_query(
    query: str,
    strategies: Optional[List[str]] = None,
) -> List[RewrittenQuery]:
    """并行跑多个策略，返回所有改写结果。

    Args:
        query: 原始 query
        strategies: 策略名列表（默认全部 6 个）

    Returns:
        List[RewrittenQuery] - 每个策略的输出
    """
    if strategies is None:
        strategies = list(STRATEGIES.keys())

    # 并行执行
    tasks = [STRATEGIES[s](query) for s in strategies if s in STRATEGIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Query rewrite strategy failed: %s", r)
            continue
        output.append(r)
    return output
