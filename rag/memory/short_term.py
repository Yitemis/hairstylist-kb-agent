# -*- coding: utf-8 -*-
"""短期记忆：上下文窗口 + 会话历史 + 压缩策略。

对应记忆架构中的"短期记忆"：保存最近的对话轮次供模型直接读取，并在超出
token 预算时通过压缩（滑窗淘汰 + 摘要卸载）控制上下文规模。

核心挑战与对策：
* Token 限制：滑动窗口只保留最近 N 轮 / 不超过 token 预算；
* 中间遗忘：溢出的旧对话不直接丢弃，而是交给上层摘要（见 manager）；
* 成本：窗口内明文、窗口外摘要，兼顾信息完整与调用成本。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rag.parsers.utils import num_tokens_from_string as count_tokens

# 单个会话窗口的默认 token 预算
DEFAULT_WINDOW_BUDGET = 1500


@dataclass
class Turn:
    """一轮对话（用户或助手的一条消息）。"""

    role: str  # "user" / "assistant"
    content: str
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = count_tokens(self.content)


@dataclass
class ShortTermMemory:
    """滑动窗口短期记忆。

    追加对话轮次，按 token 预算保留最近若干轮；被淘汰的旧轮次以列表形式
    返回，供上层做摘要卸载（不直接丢失）。
    """

    budget: int = DEFAULT_WINDOW_BUDGET
    turns: list[Turn] = field(default_factory=list)

    def add(self, role: str, content: str) -> list[Turn]:
        """追加一轮对话，返回因超预算而被淘汰的旧轮次（可能为空）。"""
        self.turns.append(Turn(role=role, content=content))
        return self._evict()

    def _evict(self) -> list[Turn]:
        """从最旧端淘汰，直到窗口内 token 不超预算。"""
        evicted: list[Turn] = []
        while self.turns and self._total_tokens() > self.budget and len(self.turns) > 1:
            evicted.append(self.turns.pop(0))
        return evicted

    def _total_tokens(self) -> int:
        return sum(t.tokens for t in self.turns)

    def render(self) -> str:
        """渲染窗口内对话为文本块。"""
        if not self.turns:
            return ""
        lines = []
        for t in self.turns:
            speaker = "用户" if t.role == "user" else "助手"
            lines.append(f"{speaker}：{t.content}")
        return "【当前对话】\n" + "\n".join(lines)

    def clear(self) -> None:
        """清空窗口。"""
        self.turns.clear()
