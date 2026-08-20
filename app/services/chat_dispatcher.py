# -*- coding: utf-8 -*-
"""Chat Dispatcher - 按 intent 路由到不同处理路径.

借鉴 JavaGuide §1.1 "范式选择":
- booking → Agentic Workflows (LangGraph 状态机)
- knowledge → ReAct (现有 chat_handler)
- casual → 单轮 LLM (无工具无状态)

借鉴 JavaGuide §10.4 "Hashimoto 实践":
- "放弃聊天模式"：让 Agent 在能读文件 / 跑程序 / 发 HTTP 的环境里直接干活
- dispatch 不应该只根据关键词, 应该看用户真正想做什么
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChatContext:
    """Dispatch 用的 context."""
    user_id: int
    session_id: str
    message: str
    history: str = ""
    role: str = "user"
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DispatchResult:
    """Dispatch 结果."""
    mode: str                       # knowledge / booking / casual
    answer: str
    sources: list[dict] = None
    options: list[dict] = None
    pending_order_id: Optional[int] = None
    extra: dict[str, Any] = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = []
        if self.options is None:
            self.options = []
        if self.extra is None:
            self.extra = {}

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "answer": self.answer,
            "sources": self.sources,
            "options": self.options,
            "pending_order_id": self.pending_order_id,
            **self.extra,
        }


# ============ Intent 分类 ============

# Booking 关键词
BOOKING_KEYWORDS = {
    "预约", "约", "订", "下单", "订单",
    "分店", "哪家店", "哪一家",
    "发型师", "找", "选", "师",
    "做头发", "做造型", "弄头发", "烫发", "染发", "剪头发",
    "明天下午", "今晚", "明天上午", "后天",
    "时间", "几点", "什么时候",
}

# Knowledge 关键词
KNOWLEDGE_KEYWORDS = {
    "原理", "为什么", "怎么", "如何", "是什么",
    "成分", "配方", "化学", "工艺", "技术",
    "区别", "对比", "哪个好", "推荐哪种",
    "护理", "保养", "受损", "修复", "掉色", "褪色",
    "过敏", "副作用", "注意事项",
    "色号", "色板", "颜色", "发型",
}

# Casual 关键词
CASUAL_KEYWORDS = {
    "你好", "在吗", "hi", "hello", "嗨",
    "谢谢", "感谢", "再见", "拜拜",
    "哈哈", "呵呵", "😀", "😂",
    "你是谁", "你能做什么", "介绍一下",
}


def classify_intent_simple(message: str) -> str:
    """简单关键词分类（fallback 用）.

    Returns:
        "booking" | "knowledge" | "casual"

    规则（按优先级）：
    1. 知识问句（"为什么"/"原理"/"是什么"）→ knowledge（即使包含美发词）
    2. booking 动作词（"预约"/"下单"/明确时间）→ booking
    3. 闲聊（"你好"/"在吗"）→ casual
    4. 兜底 knowledge
    """
    text = message.strip()
    if not text:
        return "casual"

    # 1. 知识问句优先（防止 "染发原理" 误判为 booking）
    knowledge_q_keywords = ("为什么", "原理", "是什么", "怎么", "如何", "区别", "对比", "哪个", "会", "能", "作用")
    if any(kw in text for kw in knowledge_q_keywords):
        return "knowledge"

    # 2. booking 动作（明确 + 短）
    strong_booking = ("预约", "下单", "我要约", "帮我约", "能约", "可以约", "改期", "取消订单", "退款")
    if any(kw in text for kw in strong_booking):
        return "booking"

    # 弱 booking（"分店"/"发型师"/"明天"）需要 booking 动作词配合
    weak_booking = ("分店", "发型师", "烫发", "染发", "剪头发")
    has_weak_booking = any(kw in text for kw in weak_booking)
    has_time_word = any(t in text for t in ("明天", "后天", "今晚", "明早", "明晚", "下周一", "下周二", "下周三", "下周四", "下周五", "下周六", "下周日", "周一", "周二", "周三", "周四", "周五", "周六", "周日", "点"))
    if has_weak_booking and has_time_word:
        return "booking"

    # 3. 闲聊
    if any(kw in text.lower() for kw in ("你好", "在吗", "hi", "hello", "嗨", "谢谢", "再见")):
        return "casual"

    # 4. 兜底 knowledge
    return "knowledge"


async def classify_intent_llm(message: str, history: str = "") -> str:
    """用 LLM 分类 intent（更准）.

    Returns:
        "booking" | "knowledge" | "casual"
    """
    try:
        from app.core.intent_classifier import classify_top_intent
        intent = await classify_top_intent(message, history)
        if intent in ("booking", "knowledge", "casual"):
            return intent
    except Exception as e:
        logger.debug("LLM intent classification failed: %s, fallback to keyword", e)

    return classify_intent_simple(message)


# ============ Dispatcher 主体 ============

class ChatDispatcher:
    """Chat 路由分发器.

    按 intent 路由到不同处理路径：
    - booking → run_booking_turn (LangGraph)
    - knowledge → chat_handler (现有 RAG)
    - casual → casual_handler (单轮 LLM)
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, mode: str, handler: Callable):
        """注册处理器."""
        self._handlers[mode] = handler
        logger.info("ChatDispatcher: registered handler for %s", mode)

    async def dispatch(self, ctx: ChatContext) -> DispatchResult:
        """按 intent 分发.

        决策逻辑：
        1. 如果用户在 booking 流程中（有持久化的 booking state）→ 继续 booking
        2. 否则按 LLM 分类 intent

        Args:
            ctx: ChatContext（含 user_id / message / history）

        Returns:
            DispatchResult
        """
        # 1. 检查是否在 booking 流程中
        from app.rag.workflow import get_booking_graph
        graph = get_booking_graph()
        config = {"configurable": {"thread_id": ctx.session_id}}
        try:
            saved = await graph.aget_state(config)
            if saved and saved.values:
                cur_step = saved.values.get("current_step")
                order_id = saved.values.get("order_id")
                # 在 booking 流程中（已有草稿订单 + 还没结束）
                if order_id and cur_step and cur_step not in ("aborted", "confirm"):
                    logger.info(
                        "ChatDispatcher: resuming booking step=%s order_id=%d",
                        cur_step, order_id,
                    )
                    return await self._handlers["booking"](ctx)
        except Exception as e:
            logger.debug("aget_state failed: %s", e)

        # 2. 分类
        intent = await classify_intent_llm(ctx.message, ctx.history)
        logger.info("ChatDispatcher: intent=%s user=%d msg=%s",
                   intent, ctx.user_id, ctx.message[:30])

        # 3. 路由
        handler = self._handlers.get(intent)
        if handler is None:
            # 兜底：转给 knowledge
            logger.warning("ChatDispatcher: no handler for %s, fallback to knowledge", intent)
            handler = self._handlers.get("knowledge")

        if handler is None:
            # 没有任何 handler
            return DispatchResult(
                mode="error",
                answer="系统暂未配置对话处理器，请联系管理员。",
            )

        # 3. 执行
        try:
            result = await handler(ctx)
            if isinstance(result, DispatchResult):
                return result
            elif isinstance(result, dict):
                return DispatchResult(
                    mode=intent,
                    answer=result.get("answer", ""),
                    sources=result.get("sources", []),
                    options=result.get("options", []),
                    pending_order_id=result.get("pending_order_id"),
                    extra={k: v for k, v in result.items()
                           if k not in ("answer", "sources", "options", "pending_order_id")},
                )
            else:
                return DispatchResult(mode=intent, answer=str(result))
        except Exception as e:
            logger.exception("Handler %s failed: %s", intent, e)
            return DispatchResult(
                mode=intent,
                answer=f"处理失败：{type(e).__name__}: {e}",
            )


# ============ 全局单例 + 默认处理器 ============

_dispatcher: Optional[ChatDispatcher] = None


def get_dispatcher() -> ChatDispatcher:
    """获取全局 dispatcher（懒加载默认 handlers）."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ChatDispatcher()
        _register_default_handlers(_dispatcher)
    return _dispatcher


def _register_default_handlers(d: ChatDispatcher) -> None:
    """注册默认处理器.

    - booking: run_booking_turn (LangGraph 状态机)
    - knowledge: chat_handler (现有 RAG)
    - casual: casual_handler (单轮 LLM)
    """
    from app.services.chat_service import chat_handler

    async def booking_handler(ctx: ChatContext) -> DispatchResult:
        from app.rag.workflow import run_booking_turn
        result = await run_booking_turn(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            user_input=ctx.message,
        )
        return DispatchResult(
            mode="booking",
            answer=result.get("final_message", "(无回复)"),
            pending_order_id=result.get("order_id"),
            extra={
                "current_step": result.get("current_step"),
                "iteration_count": result.get("iteration_count"),
                "missing_fields": [],
            },
        )

    async def knowledge_handler(ctx: ChatContext) -> DispatchResult:
        """Knowledge 包装 - 调 chat_handler (现有 RAG)."""
        # 构造 chat_handler 需要的 body + ctx
        body = {"message": ctx.message}
        old_ctx = type("OldCtx", (), {
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "role": ctx.role,
        })()
        result_dict = await chat_handler(body, old_ctx, enable_self_rag=False)
        return DispatchResult(
            mode="knowledge",
            answer=result_dict.get("answer", "(无回复)"),
            sources=result_dict.get("sources", []),
            extra={"self_rag": result_dict.get("self_rag", {})},
        )

    async def casual_handler(ctx: ChatContext) -> DispatchResult:
        """Casual 闲聊 - 单轮 LLM 调用."""
        from app.core.model_factory import get_model
        from agentscope.message import TextBlock, UserMsg, SystemMsg
        from app.utils.llm_extract import extract_text

        model = get_model("chat")
        sys_msg = SystemMsg(
            name="system",
            content=[TextBlock(text=(
                "你是美发智能助手。用友好、口语化的方式回答闲聊类问题。"
                "如果用户的问题与美发或预约相关，引导他们进入对应流程。"
            ))],
        )
        user_msg = UserMsg(
            name="user",
            content=[TextBlock(text=ctx.message)],
        )
        resp = await model([sys_msg, user_msg])
        text = extract_text(resp)
        return DispatchResult(mode="casual", answer=text or "(empty)")

    d.register("booking", booking_handler)
    d.register("knowledge", knowledge_handler)
    d.register("casual", casual_handler)


def reset_dispatcher() -> None:
    """重置（测试用）."""
    global _dispatcher
    _dispatcher = None


__all__ = [
    "ChatContext",
    "DispatchResult",
    "ChatDispatcher",
    "get_dispatcher",
    "reset_dispatcher",
    "classify_intent_simple",
    "classify_intent_llm",
]
