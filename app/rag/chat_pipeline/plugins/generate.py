# -*- coding: utf-8 -*-
"""GeneratePlugin: LLM 生成 + 引用约束.

职责:
  1. 拼 prompt (Context Assembler 7 步: system + facts + skill + kb + history)
  2. 调 knowledge agent 生成 answer
  3. 答案带 [1][2] 引用约束

输入:
  - ctx.context_chunks (Compress 输出)
  - ctx.facts_injection (LTM)
  - ctx.skill_injection (Skill)
  - ctx.history (压缩后)

输出:
  - ctx.answer
  - ctx.answer_tokens (估)
  - ctx.answer_latency_ms
  - ctx.sources
"""
from __future__ import annotations

import logging
import time

from app.rag.chat_pipeline.context import PipelineContext
from app.rag.chat_pipeline.plugin import Plugin

logger = logging.getLogger(__name__)


class GeneratePlugin(Plugin):
    """LLM 生成 Plugin.

    priority=80
    """

    name = "generate"
    priority = 80

    async def on_event(self, ctx: PipelineContext) -> PipelineContext:
        from app.utils.llm_extract import extract_text

        # gate refuse -> 固定回复
        if ctx.gate_decision == "refuse":
            ctx.answer = _refuse_message(ctx.gate_reason)
            ctx.sources = []
            ctx.answer_latency_ms = 0
            return ctx

        # 1. 拼 context (Context Assembler 7 步: 简化为 4 段)
        nl = "\n\n"
        ctx_text = nl.join(
            f"[{c['citation_idx']}] {c['content']}"
            for c in ctx.context_chunks
        ) or "(no results)"

        # 2. 加载长期记忆
        try:
            from app.rag.middleware.long_term_memory import load_user_facts
            user_facts = await load_user_facts(ctx.user_id)
            if user_facts:
                from app.core.long_term_memory import build_facts_injection
                ctx.facts_injection = build_facts_injection(user_facts[:20])
        except Exception as e:
            logger.debug("LTM load failed: %s", e)

        # 3. 加载 skill 注入
        try:
            from app.core.skill import build_skill_injection
            ctx.skill_injection = build_skill_injection(ctx.message) or ""
        except Exception as e:
            logger.debug("Skill injection failed: %s", e)

        # 4. 拼 full_prompt
        full_prompt = (
            (ctx.facts_injection + nl if ctx.facts_injection else "") +
            (ctx.skill_injection + nl if ctx.skill_injection else "") +
            "[KB]" + nl + ctx_text + nl +
            ("[History]" + nl + ctx.history + nl if ctx.history else "") +
            ctx.message
        )

        # 5. 调 LLM: 沿用原 ReAct agent; tool_call 卡住时降级到 chat model
        t0 = time.time()
        answer = None
        cache_hit = False

        # 5.0 LLM cache: 同样 KB + 同样 query 命中直接返回, 避免重复 LLM 调用
        try:
            from app.core.cache.llm_cache import get_llm_cache, hash_messages
            cache = get_llm_cache()
            cache_key_payload = {
                "ctx_text": ctx_text,
                "history": ctx.history or "",
                "facts": ctx.facts_injection or "",
                "skill": ctx.skill_injection or "",
                "query": ctx.message,
                "version_tag": ctx.version_tag,
            }
            cache_key = hash_messages([cache_key_payload], model="generate_plugin")
            cached = cache.get(cache_key)
            if cached:
                answer = cached.get("answer", "")
                cache_hit = True
                logger.info("Generate: cache HIT key=%s", cache_key[:16])
        except Exception as e:
            logger.debug("Cache check failed (ignore): %s", e)

        if not cache_hit:
            try:
                from app.core.knowledge_agent_factory import get_knowledge_agent
                from agentscope.message import TextBlock, UserMsg

                agent = await get_knowledge_agent()
                user_msg = UserMsg(
                    name="user",
                    content=[TextBlock(text=full_prompt)],
                )
                resp = await agent.reply([user_msg])
                answer = extract_text(resp)
            except Exception as e:
                # ReAct agent 偶发 tool_call 等待 (AgentScope 已知问题)
                logger.warning("ReAct agent failed, fallback to direct chat: %s", e)

        # 检测 ReAct 卡在 tool_call 等待 (返回固定字符串)
        if not answer or "waiting for your permission" in (answer or "").lower() or "external execution" in (answer or "").lower():
            logger.warning("ReAct returned waiting/external message, fallback to chat model")
            try:
                from app.core.model_factory import get_model
                from agentscope.message import TextBlock, UserMsg, SystemMsg
                chat_model = get_model("chat")
                sys_msg = SystemMsg(
                    name="system",
                    content=[TextBlock(text=(
                        "你是美发行业专业知识助手。基于 [KB] 引用的知识库内容回答用户问题。"
                        "要求: 1) 引用 [1][2] 标注 2) 简洁专业 3) 不编造 KB 外的信息"
                    ))],
                )
                user_msg = UserMsg(
                    name="user",
                    content=[TextBlock(text=full_prompt)],
                )
                resp = await chat_model([sys_msg, user_msg])
                # chat model 返回 async_generator, 需要 iterate 收集文本
                # 去重: streaming 可能 delta + cumulative 混发, 用 dedup_by_prefix 只保最长 prefix
                if hasattr(resp, "__aiter__"):
                    chunks = []
                    async for chunk in resp:
                        text = None
                        if hasattr(chunk, "content"):
                            for block in (chunk.content or []):
                                if hasattr(block, "text") and block.text:
                                    text = block.text
                                    break
                        elif isinstance(chunk, str):
                            text = chunk
                        if not text:
                            continue
                        # 去重: 如果新 text 以已收集的 prefix 开头, 只取 suffix
                        prefix = "".join(chunks)
                        if text.startswith(prefix):
                            chunks.append(text[len(prefix):])
                        elif prefix.startswith(text) and len(text) > 0:
                            # 反向: 新 text 比 prefix 短, 可能是回退, 跳过
                            continue
                        else:
                            # 完全不同的内容, 追加
                            chunks.append(text)
                    answer = "".join(chunks) or "(empty)"
                else:
                    answer = extract_text(resp) or "(empty)"
            except Exception as e:
                logger.exception("Fallback chat model failed: %s", e)
                answer = f"抱歉, 答案生成失败: {type(e).__name__}: {e}"
                ctx.error = f"generate: {e}"

        # 写回 LLM cache (避免下次同样 query 又调 LLM)
        if answer and not cache_hit and not answer.startswith("抱歉"):
            try:
                from app.core.cache.llm_cache import get_llm_cache
                cache = get_llm_cache()
                cache.set(cache_key, {"answer": answer, "cached_at": time.time()})
                logger.info("Generate: cache STORE key=%s", cache_key[:16])
            except Exception as e:
                logger.debug("Cache store failed (ignore): %s", e)

        ctx.answer = answer
        ctx.answer_latency_ms = int((time.time() - t0) * 1000)

        # 6. sources (top context_top_n)
        ctx.sources = [
            {
                "document_id": c.get("document_id", ""),
                "score": round(float(c.get("score", 0)), 4),
                "content": c.get("content", "")[:300],
                "citation_idx": c.get("citation_idx", i + 1),
            }
            for i, c in enumerate(ctx.context_chunks)
        ]

        logger.info(
            "Generate: answer=%d chars %dms citations=%d",
            len(answer), ctx.answer_latency_ms, len(ctx.sources),
        )
        return ctx


def _refuse_message(reason: str) -> str:
    """Gate refuse 时的固定回复."""
    if reason == "no_candidates":
        return "抱歉, 知识库中没有找到相关信息。请换个问法, 或联系发型师。"
    if reason == "noise_too_high":
        return "抱歉, 检索结果相关性过低, 暂无法给出可靠答案。"
    if reason == "booking_intent_use_langgraph":
        return ""  # 不抢 booking 流程
    if reason == "empty_message":
        return "请告诉我您想了解什么?"
    return f"无法回答 ({reason})"


__all__ = ["GeneratePlugin"]
