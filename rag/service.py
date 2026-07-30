# -*- coding: utf-8 -*-
"""RAG 端到端服务：检索 + Context 工程 + 记忆 + 生成。

把各模块串成一次完整问答：

1. 记忆：取回长期事实 + 会话摘要 + 当前窗口；
2. 检索：混合检索命中父块（:mod:`rag.searcher`）；
3. Context 工程：拼装带溯源的知识库上下文（:mod:`rag.context`）；
4. 生成：组装最终 Prompt 交对话模型作答；
5. 回写记忆：把本轮问答写回记忆，触发压缩与事实抽取。

对外暴露 :class:`RagService`：一个租户/用户维度的会话级服务实例。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rag.context import build_answer_prompt, build_context
from rag.memory import MemoryManager
from rag.searcher import SearchHit, search

logger = logging.getLogger(__name__)

_SYSTEM_ROLE = (
    "你是一名资深美发行业技术顾问，服务发型师与门店员工。"
    "请依据【知识库参考内容】专业、准确地回答，可结合【已确认的用户信息】"
    "与【会话摘要】做个性化回答；参考内容不足时如实说明，不得编造产品或数据。"
)


@dataclass
class AnswerResult:
    """一次问答的完整结果（含可观测中间产物）。"""

    answer: str
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    context: str = ""
    prompt: str = ""
    rerank_applied: bool = False
    elapsed_ms: int = 0


class RagService:
    """会话级 RAG 服务（一个 tenant/user 一个实例）。"""

    def __init__(
        self,
        tenant_id: str = "default",
        user_id: str = "default",
        roles: set[str] | None = None,
    ) -> None:
        """初始化会话服务。

        Args:
            tenant_id: 租户 ID（数据隔离）。
            user_id: 用户 ID（记忆分区）。
            roles: 用户角色集合（权限过滤）。
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.roles = roles
        self.memory = MemoryManager(tenant_id=tenant_id, user_id=user_id)

    async def answer(
        self,
        query: str,
        *,
        top_k: int = 5,
        enable_rerank: bool = True,
        context_budget: int = 3000,
    ) -> AnswerResult:
        """执行一次完整问答。

        Args:
            query: 用户问题。
            top_k: 检索返回父块数。
            enable_rerank: 是否 Rerank 精排。
            context_budget: 知识库上下文 token 预算。

        Returns:
            AnswerResult。
        """
        import time

        start = time.time()

        # 1) 记录用户输入并取记忆块
        await self.memory.add_user(query)
        memory_block = self.memory.render_memory_block()

        # 2) 混合检索
        result = await search(
            query,
            tenant_id=self.tenant_id,
            roles=self.roles,
            top_k=top_k,
            enable_rerank=enable_rerank,
        )

        # 3) Context 工程
        context = build_context(result.hits, budget=context_budget)

        # 4) 组装 Prompt 并生成
        prompt = build_answer_prompt(
            query, context, memory_block=memory_block, system_role=_SYSTEM_ROLE,
        )
        answer = await self._generate(prompt)

        # 5) 回写记忆
        await self.memory.add_assistant(answer)

        return AnswerResult(
            answer=answer,
            query=query,
            hits=result.hits,
            context=context,
            prompt=prompt,
            rerank_applied=result.rerank_applied,
            elapsed_ms=int((time.time() - start) * 1000),
        )

    async def _generate(self, prompt: str) -> str:
        """调用对话模型生成回答；未配置时返回占位提示。"""
        try:
            from openai import AsyncOpenAI

            from app.core.config import chat_config

            if not chat_config.is_valid:
                return "（对话模型未配置，无法生成回答。）"
            client = AsyncOpenAI(
                api_key=chat_config.api_key, base_url=chat_config.base_url,
            )
            resp = await client.chat.completions.create(
                model=chat_config.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=120,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("生成回答失败: %s", exc)
            return f"（生成回答时出错：{exc}）"
