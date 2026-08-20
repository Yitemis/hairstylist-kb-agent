# -*- coding: utf-8 -*-
"""上下文利用率监控：Token 计数 + 40% 阈值告警.

借鉴 JavaGuide §2.3 "上下文利用率 40% 阈值":
- Smart Zone (0-40%)：推理聚焦、工具调用准确
- Dumb Zone (>40%)：幻觉增多、兜圈子、格式混乱

借鉴 JavaGuide §3.7 "Token 预算优先级":
- 低优先级（可折叠）：早期对话历史
- 中优先级（可精简）：RAG 背景、旧工具结果
- 高优先级（固定区）：System Constraints、当前任务目标、安全边界

借鉴 JavaGuide §10.2 "Anthropic 实践":
- Sonnet 4.5 在上下文快满时草草收尾（"上下文焦虑"）
- 解法：context resets - 清窗口 + 结构化交接
- 我们阈值：>40% warn, >60% compress, >80% reset

实现：
- 用 tiktoken 准确计数（fallback 到字符数 / 4 估算）
- 监控 metrics: context_utilization
- 输出告警 log + 返回建议
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ============ 配置 ============

# 主流模型上下文窗口大小（保守值）
MODEL_CONTEXT_WINDOWS = {
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "claude-3-haiku": 200000,
    "claude-3-sonnet": 200000,
    "claude-3.5-sonnet": 200000,
    "claude-sonnet-4.5": 200000,
    "deepseek-chat": 64000,
    "deepseek-v3": 64000,
    "doubao-pro": 32000,
    "qwen-turbo": 32000,
    "qwen-plus": 128000,
    "default": 32000,  # 保守默认
}

# 告警阈值
SMART_ZONE_LIMIT = 0.40  # Smart Zone 上限（超过就 Dumb Zone）
COMPRESS_THRESHOLD = 0.60  # 触发压缩
RESET_THRESHOLD = 0.80  # 触发 context reset


# ============ 阈值枚举 ============

class ContextZone(str, Enum):
    """上下文利用率区间."""

    SMART = "smart"          # 0-40% 推理聚焦
    DUMB = "dumb"            # 40-60% 注意力分散
    COMPRESS = "compress"    # 60-80% 触发压缩
    RESET = "reset"          # 80%+ 触发 context reset


@dataclass
class ContextUsage:
    """上下文使用情况."""

    used_tokens: int
    max_tokens: int
    utilization: float  # 0.0 - 1.0
    zone: ContextZone
    recommendation: str  # 建议下一步动作

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    def to_dict(self) -> dict:
        return {
            "used_tokens": self.used_tokens,
            "max_tokens": self.max_tokens,
            "utilization": round(self.utilization, 3),
            "zone": self.zone.value,
            "recommendation": self.recommendation,
            "remaining_tokens": self.remaining_tokens,
        }


# ============ Token 计数 ============

_TOKENIZER = None
_TOKENIZER_NAME = None


def _get_tokenizer(model_name: str = "default"):
    """懒加载 tiktoken tokenizer.

    如果 tiktoken 没装或模型不支持, fallback 到字符估算.
    """
    global _TOKENIZER, _TOKENIZER_NAME
    if _TOKENIZER is not None and _TOKENIZER_NAME == model_name:
        return _TOKENIZER

    try:
        import tiktoken
        # OpenAI 模型用 o200k_base（GPT-4o 系列）/ cl100k_base（GPT-4 / 3.5）
        if "gpt-4o" in model_name or "gpt-5" in model_name:
            _TOKENIZER = tiktoken.get_encoding("o200k_base")
        elif "gpt-4" in model_name or "gpt-3.5" in model_name:
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        else:
            # 其他模型 fallback
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        _TOKENIZER_NAME = model_name
        return _TOKENIZER
    except ImportError:
        logger.debug("tiktoken not installed, using char/4 estimate")
        return None


def count_tokens(text: str, model_name: str = "default") -> int:
    """计算文本的 Token 数.

    Args:
        text: 输入文本
        model_name: 模型名（用于选 tokenizer）

    Returns:
        Token 数（估算）
    """
    if not text:
        return 0

    tokenizer = _get_tokenizer(model_name)
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text))
        except Exception as e:
            logger.debug("tiktoken encode failed: %s", e)

    # Fallback：英文按词数, 中文按字数, 混合按 1 字符 = 1.5 token
    if not text.strip():
        return 0
    cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
    en_words = sum(1 for c in text if c.isascii() and c.isalnum())
    other = len(text) - cn_chars - en_words
    return cn_chars + int(en_words * 0.75) + int(other * 0.5)


def count_messages_tokens(messages: list, model_name: str = "default") -> int:
    """计算消息列表的总 Token 数.

    Args:
        messages: list of {role, content} or BaseMessage

    Returns:
        总 Token 数
    """
    total = 0
    for msg in messages:
        # 提取 content
        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                total += count_tokens(content, model_name)
            elif isinstance(content, list):
                # ContentBlock list
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += count_tokens(block["text"], model_name)
                    elif hasattr(block, "text"):
                        total += count_tokens(block.text, model_name)
            # role 开销 ~4 token
            total += 4
        elif isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                total += count_tokens(content, model_name)
            total += 4  # role 开销
    return total


# ============ 主要 API ============

def get_context_usage(
    used_tokens: int,
    model_name: str = "default",
) -> ContextUsage:
    """评估当前上下文使用情况.

    Args:
        used_tokens: 已用 Token 数
        model_name: 模型名（用于查 context window）

    Returns:
        ContextUsage 对象（含 utilization, zone, recommendation）
    """
    max_tokens = MODEL_CONTEXT_WINDOWS.get(model_name, MODEL_CONTEXT_WINDOWS["default"])
    utilization = used_tokens / max_tokens if max_tokens > 0 else 0.0

    if utilization >= RESET_THRESHOLD:
        zone = ContextZone.RESET
        recommendation = (
            "⚠️ 上下文利用率 >80%，强烈建议触发 context reset："
            "清空对话窗口 + 结构化交接任务状态到 NOTES.md，让新 Agent 继续。"
        )
    elif utilization >= COMPRESS_THRESHOLD:
        zone = ContextZone.COMPRESS
        recommendation = (
            "⚠️ 上下文利用率 >60%，建议压缩："
            "早期对话历史做摘要，丢弃冗余工具结果。"
        )
    elif utilization >= SMART_ZONE_LIMIT:
        zone = ContextZone.DUMB
        recommendation = (
            "⚠️ 上下文利用率 >40%，已进入 Dumb Zone："
            "模型可能注意力分散、工具调用变慢。考虑手动压缩或提前结束任务。"
        )
    else:
        zone = ContextZone.SMART
        recommendation = "✅ 上下文利用率 <40%，处于 Smart Zone，推理质量稳定。"

    return ContextUsage(
        used_tokens=used_tokens,
        max_tokens=max_tokens,
        utilization=utilization,
        zone=zone,
        recommendation=recommendation,
    )


def check_and_warn(
    text_or_messages,
    model_name: str = "default",
    user_id: Optional[int] = None,
) -> ContextUsage:
    """检查并记录告警.

    Args:
        text_or_messages: 文本字符串 或 消息列表
        model_name: 模型名
        user_id: 用户 ID（用于 log）

    Returns:
        ContextUsage 对象
    """
    if isinstance(text_or_messages, str):
        tokens = count_tokens(text_or_messages, model_name)
    elif isinstance(text_or_messages, list):
        tokens = count_messages_tokens(text_or_messages, model_name)
    else:
        tokens = 0

    usage = get_context_usage(tokens, model_name)

    # 告警 log
    if usage.zone != ContextZone.SMART:
        logger.warning(
            "Context %s zone hit: user=%s used=%d max=%d util=%.1f%%",
            usage.zone.value, user_id, usage.used_tokens, usage.max_tokens,
            usage.utilization * 100,
        )
    else:
        logger.debug(
            "Context smart: user=%s used=%d max=%d util=%.1f%%",
            user_id, usage.used_tokens, usage.max_tokens,
            usage.utilization * 100,
        )

    return usage


# ============ 压缩辅助 ============

def should_compress(usage: ContextUsage) -> bool:
    """是否应该触发压缩."""
    return usage.zone in (ContextZone.COMPRESS, ContextZone.RESET)


def should_reset(usage: ContextUsage) -> bool:
    """是否应该触发 context reset."""
    return usage.zone == ContextZone.RESET


# ============ 装饰器 / Hook ============

def monitor_context(model_name: str = "default"):
    """装饰器：在调用 LLM 前自动检查上下文利用率.

    用法:
        @monitor_context()
        async def call_llm(messages):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 找 messages 参数
            messages = kwargs.get("messages") or (args[0] if args else None)
            if messages is not None:
                usage = check_and_warn(messages, model_name)
                # 把 usage 挂到 kwargs 供 func 使用
                kwargs["_context_usage"] = usage
            return await func(*args, **kwargs)
        return wrapper
    return decorator


__all__ = [
    "MODEL_CONTEXT_WINDOWS",
    "SMART_ZONE_LIMIT",
    "COMPRESS_THRESHOLD",
    "RESET_THRESHOLD",
    "ContextZone",
    "ContextUsage",
    "count_tokens",
    "count_messages_tokens",
    "get_context_usage",
    "check_and_warn",
    "should_compress",
    "should_reset",
    "monitor_context",
]
