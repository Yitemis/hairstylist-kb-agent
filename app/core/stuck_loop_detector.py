# -*- coding: utf-8 -*-
"""Stuck Loop Detector: Agent 循环防 LLM 抽风死循环.

借鉴 WeKnora engine.go (Section 5.4: consecutiveSameContent 检测).

Why?
- LLM 偶尔返回同样的 content (e.g. "我再想想" 重复 100 次)
- 工具调用也可能卡在同样的 result 上
- 我们的 Agent 之前没有 stuck 检测, 极端情况会无限循环
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StuckState:
    """Stuck 检测的内部状态."""
    last_content: Optional[str] = None
    last_content_normalized: Optional[str] = None
    consecutive_count: int = 0
    last_tool_signature: Optional[str] = None
    tool_repeat_count: int = 0
    started_at: float = field(default_factory=time.time)

    def reset(self) -> None:
        """重置所有状态."""
        self.last_content = None
        self.last_content_normalized = None
        self.consecutive_count = 0
        self.last_tool_signature = None
        self.tool_repeat_count = 0
        self.started_at = time.time()


class StuckLoopDetector:
    """Stuck Loop 检测器.

    检测两类 stuck:
    1. **Content Stuck**: 同一个 content 连续出现 N 次
    2. **Tool Stuck**: 同一个 tool call (同名 + 同参数) 连续出现 N 次

    任一触发即返回 stuck, 上层应 break Agent 循环.

    Args:
        max_consecutive: 同 content 最多连续 N 次 (默认 3)
        max_tool_repeat: 同 tool call 最多连续 N 次 (默认 3)
        content_normalize: 是否 trim + lowercase 后比较 (默认 True)
    """

    def __init__(
        self,
        max_consecutive: int = 3,
        max_tool_repeat: int = 3,
        content_normalize: bool = True,
    ):
        if max_consecutive < 1:
            raise ValueError(f"max_consecutive must >= 1, got {max_consecutive}")
        if max_tool_repeat < 1:
            raise ValueError(f"max_tool_repeat must >= 1, got {max_tool_repeat}")
        self.max_consecutive = max_consecutive
        self.max_tool_repeat = max_tool_repeat
        self.content_normalize = content_normalize
        self.state = StuckState()

    def _normalize(self, content: str) -> str:
        if not self.content_normalize:
            return content
        return (content or "").strip().lower()

    def check_content(self, content: str) -> bool:
        """检查 content 是否 stuck.

        Args:
            content: Agent 当前的输出 content

        Returns:
            True if stuck (需要 break), False if OK
        """
        norm = self._normalize(content)
        if not norm:
            # 空 content 不算 stuck
            return False

        if norm == self.state.last_content_normalized:
            self.state.consecutive_count += 1
            if self.state.consecutive_count >= self.max_consecutive:
                logger.warning(
                    "StuckLoopDetector: 连续 %d 次相同 content, 触发 break",
                    self.state.consecutive_count,
                )
                return True
        else:
            self.state.consecutive_count = 1
            self.state.last_content_normalized = norm
            self.state.last_content = content
        return False

    def check_tool_call(self, tool_name: str, tool_args: Optional[dict] = None) -> bool:
        """检查 tool call 是否 stuck.

        Args:
            tool_name: 工具名
            tool_args: 工具参数 dict (用于区分同工具不同参数)

        Returns:
            True if stuck, False if OK
        """
        # 构造 tool signature: name + sorted args
        if tool_args:
            sig = f"{tool_name}::{sorted(tool_args.items())}"
        else:
            sig = tool_name

        if sig == self.state.last_tool_signature:
            self.state.tool_repeat_count += 1
            if self.state.tool_repeat_count >= self.max_tool_repeat:
                logger.warning(
                    "StuckLoopDetector: 连续 %d 次相同 tool call (%s), 触发 break",
                    self.state.tool_repeat_count, tool_name,
                )
                return True
        else:
            self.state.tool_repeat_count = 1
            self.state.last_tool_signature = sig
        return False

    def reset(self) -> None:
        """重置状态 (新会话开始)."""
        self.state.reset()

    def get_stats(self) -> dict:
        """获取当前状态 (用于调试 / 监控)."""
        return {
            "consecutive_count": self.state.consecutive_count,
            "tool_repeat_count": self.state.tool_repeat_count,
            "elapsed_sec": time.time() - self.state.started_at,
        }


__all__ = [
    "StuckLoopDetector",
    "StuckState",
]
